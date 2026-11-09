#!/usr/bin/env python3
"""Agent proxy: OpenAI-совместимый эндпоинт, который сам вызывает инструменты.

Зачем: Open WebUI в нашей версии не запускает веб-поиск, а llama-server умеет
нативный tool calling. Прокси принимает запрос как OpenAI, даёт модели набор
инструментов, выполняет вызовы и возвращает готовый ответ.

Порт 8085, только loopback. Зависимостей нет — стандартная библиотека.
"""
import base64
import json
import os
import re
import subprocess
import threading

# Очередь обращений к органу (одна GPU — обработка последовательно)
LLM_LOCK = threading.Lock()
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
sys.path.append("<AINE_HOME>/vokivon/aine")
try:
    from ail import AineAilEngine, barrier_check, barrier_check_llm
except Exception:
    AineAilEngine = None
    barrier_check = lambda *a, **k: (True, '')
    barrier_check_llm = lambda *a, **k: (False, '')

UPSTREAM = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080")
FAST_URL = os.environ.get("FAST_URL", "http://127.0.0.1:8095")
API_KEY = os.environ.get("LLAMA_API_KEY", "")
SEARX = os.environ.get("SEARX_URL", "http://127.0.0.1:8088")
PORT = int(os.environ.get("PROXY_PORT", "8085"))
BIND_ADDR = os.environ.get("BIND_ADDR", "127.0.0.1")
PROXY_TOKEN = os.environ.get("PROXY_TOKEN", "")
PASSTHROUGH = os.environ.get("PASSTHROUGH", "0") == "1"
MAX_ROUNDS = int(os.environ.get("PROXY_MAX_ROUNDS", "8"))
THINKING = os.environ.get("AGENT_THINKING", "0") == "1"

# Трейсинг в Langfuse (включается только при заданном LANGFUSE_HOST)
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

VISION_URL = os.environ.get("VISION_URL", "http://127.0.0.1:8082")
VISION_MODEL = os.environ.get("VISION_MODEL", "vision")
SD_URL = os.environ.get("SD_URL", "http://127.0.0.1:7860")
IMG_SIZE = os.environ.get("IMG_SIZE", "768x768")
IMG_STEPS = int(os.environ.get("IMG_STEPS", "4"))
CHAT_MODEL = os.environ.get("CHAT_MODEL", "Qwen3.6-35B-A3B-UD-Q4_K_M")
DEEP_MODEL = os.environ.get("DEEP_MODEL", "Qwen3.6-35B-A3B-UD-Q4_K_M")
DEEP_WORDS = ["создай", "напиши", "проанализируй", "сделай", "разработай",
              "исправь", "сгенерируй", "вычисли", "проверь", "оптимизируй",
              "найди ошибку", "код", "программ", "скрипт", "отчёт", "таблиц",
              "структур", "штатн", "финанс", "произведи", "построй", "собери"]


def _is_simple(body):
    """Простой вопрос → голос (быстро); сложная задача → орган (глубоко)."""
    try:
        msgs = body.get("messages") or []
        last = next((m.get("content") for m in reversed(msgs)
                     if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        low = (last or "").lower()
        return not any(w in low for w in DEEP_WORDS)
    except Exception:
        return True
CODE_MODEL = os.environ.get("CODE_MODEL", "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M")

CODE_RE = re.compile(
    r"(?:\bкод\b|\bфункци|\bкласс\b|\bскрипт|\bбаг|\bошибк|\bрефактор|\bтест|\bюнит|"
    r"\bpython\b|\bjavascript\b|\btypescript\b|\bсql\b|\bsql\b|\bbash\b|\bdocker\b|\bapi\b|"
    r"\bjson\b|\bверстк|\bcss\b|\bhtml\b|\bgit\b|\bregex\b|\bпарсер|"
    r"\bкалькулятор|\bпрограмм|\bприложен|\bсайт|\bбот\b|\bигр[ауы]\b|\bскрипт|\bмодул)", re.I)
IMG_RE = re.compile(
    r"(?:нарису|сгенериру|создай).{0,40}(?:картин|изображен|логотип|иллюстрац|обложк|иконк|арт)|"
    r"\bdraw\b|\bgenerate\b.{0,30}\bimage\b", re.I)


def _text_of(messages):
    parts = []
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text") or "")
    return " ".join(parts)


def _has_image(messages):
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, list) and any(
                isinstance(p, dict) and p.get("type") in ("image_url", "input_image") for p in c):
            return True
    return False


def pick_route(body):
    msgs = body.get("messages") or []
    if _has_image(msgs):
        return "vision"
    text = _text_of(msgs)
    if IMG_RE.search(text):
        return "image"
    if CODE_RE.search(text):
        return "code"
    return "chat"


def call_vision(body):
    payload = {
        "model": VISION_MODEL,
        "messages": body.get("messages") or [],
        "max_tokens": int(body.get("max_tokens") or 800),
        "stream": False,
        "temperature": 0.2,
    }
    data = http_json(VISION_URL + "/v1/chat/completions", payload=payload,
                     headers={"Authorization": f"Bearer {API_KEY}"}, timeout=600)
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    return text, [{"tool": "vision", "title": "Qwen2.5-VL"}]


IMAGE_SYSTEM = (
    "Ты — промпт-инженер для Stable Diffusion XL. Преобразуй просьбу пользователя "
    "в один английский промпт: главный объект, стиль, композиция, фон, освещение. "
    "Без вводных слов и кавычек, максимум 45 слов. Выведи только промпт."
)


def _save_image(b64):
    import base64 as _b64, time as _time, os as _os
    d = "<AINE_HOME>/workspace/images"
    _os.makedirs(d, exist_ok=True)
    fn = "gen_%d.png" % int(_time.time() * 1000)
    with open(_os.path.join(d, fn), "wb") as f:
        f.write(_b64.b64decode(b64))
    return "https://<your-domain>/img/" + fn


def _image_prompt(user_text):
    """Переформулировать разговорную просьбу в промпт для SDXL (через локальную LLM)."""
    try:
        data = http_json(
            UPSTREAM + "/v1/chat/completions", timeout=90,
            payload={
                "model": CHAT_MODEL, "max_tokens": 160, "temperature": 0.4, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [
                    {"role": "system", "content": IMAGE_SYSTEM},
                    {"role": "user", "content": str(user_text)[:600]},
                ],
            },
            headers={"Authorization": f"Bearer {API_KEY}"})
        out = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        out = out.strip().strip('"').strip()
        if len(out) > 8:
            return out, str(user_text)[:200]
    except Exception:
        pass
    return str(user_text), str(user_text)[:200]


def generate_image(body):
    raw = _text_of(body.get("messages") or []).strip()[-600:]
    raw = raw or "abstract illustration"
    prompt, shown = _image_prompt(raw)
    w, h = 768, 768
    try:
        w, h = [int(x) for x in IMG_SIZE.lower().split("x")]
    except Exception:
        pass
    # Родной A1111-совместимый API: даёт управлять шагами (4 вместо 20 → в 5 раз быстрее)
    try:
        data = http_json(SD_URL + "/sdapi/v1/txt2img", timeout=600, payload={
            "prompt": prompt, "steps": IMG_STEPS, "cfg_scale": 1.0,
            "width": w, "height": h, "sampler_name": "Euler a",
        })
        imgs = data.get("images") or []
        if imgs:
            return (f"![{shown[:60]}]({_save_image(imgs[0])})\n\n"
                    f"*SDXL-Turbo, {w}×{h}, {IMG_STEPS} шага · промпт: `{prompt[:150]}`*")
    except Exception:
        pass
    # Резерв: OpenAI-совместимый маршрут
    try:
        data = http_json(SD_URL + "/v1/images/generations", timeout=600,
                         payload={"prompt": prompt, "n": 1, "size": f"{w}x{h}"})
        item = (data.get("data") or [{}])[0]
        b64 = item.get("b64_json")
        if b64:
            return (f"![{shown[:60]}]({_save_image(b64)})\n\n"
                    f"*Сгенерировано локально (SDXL-Turbo): {shown[:120]}*")
        if item.get("url"):
            return f"![{shown[:60]}]({item['url']})\n\n*Сгенерировано: {shown[:120]}*"
    except Exception as e:
        return ("Не удалось сгенерировать изображение: сервер картинок занят или упал "
                f"({type(e).__name__}). Попробуйте ещё раз через минуту.")
    return "Сервер изображений не вернул картинку."


_MODELS = {"ts": 0.0, "ids": set()}
PERSONA_MODELS = {"coder": None, "reviewer": None}  # заполняется ниже CODE_MODEL


def _upstream_models():
    now = time.time()
    if not _MODELS["ids"] or now - _MODELS["ts"] > 300:
        try:
            data = http_json(UPSTREAM + "/v1/models",
                             headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
            _MODELS["ids"] = {m.get("id") for m in (data.get("data") or []) if m.get("id")}
            _MODELS["ts"] = now
        except Exception:
            pass
    return _MODELS["ids"]


def resolve_model(name):
    """Клиент может прислать id персоны Open WebUI («coder»), которого нет в llama-server.

    Тогда подставляем базовую модель, иначе llama-server ответит 400.
    """
    name = (name or "").strip()
    ids = _upstream_models()
    if not ids or name in ids:
        return name
    if name in ("coder", "reviewer"):
        return CODE_MODEL
    if name in ("excel", "writer", "docs", "planner", "auto", ""):
        return CHAT_MODEL
    return CHAT_MODEL


def dispatch(body):
    model = (body.get("model") or "").strip()
    route = pick_route(body) if model in ("", "auto") else "chat"
    if route == "vision":
        text, used = call_vision(body)
        return text, [{"tool": "router", "title": "photo → vision (Qwen2.5-VL)"}] + used, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if route == "image":
        return generate_image(body), [{"tool": "router", "title": "image → SDXL-Turbo"},
                                      {"tool": "image_gen", "title": "SDXL-Turbo"}], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if route == "code":
        chosen = CODE_MODEL
    elif model in ("", "auto"):
        chosen = CHAT_MODEL if _is_simple(body) else DEEP_MODEL
    else:
        chosen = resolve_model(model)
    text, used, usage = run_agent(dict(body, model=chosen))
    return text, [{"tool": "router", "title": f"{route} → {chosen}"}] + used, usage

UA = "Mozilla/5.0 (X11; Linux x86_64) agent-proxy/1.0"

# ── Память разума (геном/пыльца) ────────────────────────────────
_GENOME_PATH = "<AINE_HOME>/workspace/aine/ail/genome.json"
_RESONANCE_MIN = 0.4
SELF_REFLECT = os.environ.get("SELF_REFLECT", "0") == "1"


def self_reflect(text, answer):
    """Саморефлексия: проверщик критикует ответ, при «НЕТ» — улучшение."""
    if not text or not answer:
        return answer, False
    critic = ('Ты — строгий проверщик. Оцени ответ на запрос. Ответь ТОЛЬКО "ДА" (хорош) '
              'или "НЕТ" (плох) и одной фразой почему. Запрос: ' + text + ' Ответ: ' + answer)
    try:
        c = call_upstream([{"role": "user", "content": critic}], [], CHAT_MODEL, 150)
        ct = ((c.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception:
        return answer, False
    if "НЕТ" not in ct and "нет" not in ct.lower():
        return answer, False
    imp = ('Улучши ответ, устранив замечания проверщика. Дай ТОЛЬКО исправленный ответ. '
           'Запрос: ' + text + ' Ответ: ' + answer + ' Замечание: ' + ct)
    try:
        r = call_upstream([{"role": "user", "content": imp}], [], CHAT_MODEL, 800)
        it = ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception:
        return answer, False
    return (it.strip() or answer), True
_engine = None
_engine_lock = threading.Lock()


def _resonate(text):
    """Ответ из накопленной пыльцы (резонанс). None — если нет совпадения."""
    global _engine
    if AineAilEngine is None:
        return None
    try:
        if _engine is None:
            with _engine_lock:
                if _engine is None:
                    _engine = AineAilEngine(_GENOME_PATH)
                    _engine.load()
        r = _engine.resonate(text)
        if r and r.get("resonance", 0) >= _RESONANCE_MIN:
            with _engine_lock:
                _engine.save()
            return r
    except Exception:
        pass
    return None

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Поиск в интернете. Используй для новостей, фактов, цен, событий, всего что могло измениться.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Текущая погода в городе: температура, ветер, влажность.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "Название города"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Показать файлы в рабочей папке пользователя (путь относительно неё).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Путь, по умолчанию '.'"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Прочитать текстовый файл из рабочей папки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "max_chars": {"type": "integer", "description": "Лимит символов, по умолчанию 6000"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Создать или перезаписать текстовый файл в рабочей папке.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "content": {"type": "string", "description": "Полное содержимое файла"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Выполнить shell-команду в рабочей папке (без sudo). Возвращает stdout+stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Команда целиком"},
                    "timeout": {"type": "integer", "description": "Секунды, по умолчанию 60"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": "Git-операция в рабочей папке: status, diff, log, add, commit -m.",
            "parameters": {
                "type": "object",
                "properties": {"args": {"type": "string", "description": "Аргументы git, например 'status --short'"}},
                "required": ["args"],
            },
        },
    },
]

WMO = {
    0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "облачно",
    45: "туман", 48: "изморозь", 51: "слабая морось", 53: "морось", 55: "сильная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь", 66: "ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "ливень", 81: "сильный ливень", 82: "очень сильный ливень",
    85: "снегопад", 86: "сильный снегопад", 95: "гроза", 96: "гроза с градом",
    99: "сильная гроза с градом",
}


def http_json(url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            body = ""
        print(f"http_json {e.code} {url}: {body}", flush=True)
        raise


def tool_web_search(query, count=5):
    q = urllib.parse.quote(str(query))
    url = f"{SEARX}/search?q={q}&format=json&language=ru"
    data = http_json(url, timeout=12)
    out = []
    for i, r in enumerate((data.get("results") or [])[:count], 1):
        title = (r.get("title") or "").strip()
        body = re.sub(r"\s+", " ", (r.get("content") or "")).strip()
        out.append(f"{i}. {title}\n   {body}\n   {r.get('url', '')}")
    return "\n".join(out) if out else "Поиск не дал результатов."


def _wttr_fallback(city):
    """Резервный источник погоды: короткий текстовый ответ wttr.in."""
    try:
        url = "https://wttr.in/%s?format=%%l:+%%c+%%t+%%f+%%w" % urllib.parse.quote(str(city))
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "curl/8"}), timeout=8).read()
        text = raw.decode("utf-8", "replace").strip()
        if text and "%" not in text and "Unknown location" not in text:
            return text + " (источник: wttr.in)."
    except Exception:
        pass
    return ""


WEATHER_CACHE = {}
WEATHER_TTL = 600


def tool_get_weather(city):
    key = str(city).strip().lower()
    hit = WEATHER_CACHE.get(key)
    if hit and time.time() - hit[0] < WEATHER_TTL:
        return hit[1] + " (из кэша)"
    try:
        geo = http_json(
            "https://geocoding-api.open-meteo.com/v1/search?name="
            + urllib.parse.quote(str(city)) + "&count=1&language=ru&format=json",
            timeout=8,
        )
        res = geo.get("results") or []
        if not res:
            return f"Город «{city}» не найден. Попробуй web_search."
        g = res[0]
        fc = http_json(
            "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            "wind_speed_10m,weather_code&timezone=auto" % (g["latitude"], g["longitude"]),
            timeout=8,
        )
        c = fc.get("current") or {}
        if c.get("temperature_2m") is None:
            raise ValueError("нет поля temperature_2m")
        desc = WMO.get(int(c.get("weather_code", -1)), "без описания")
        text = (
            f"{g['name']} ({g.get('country', '')}): {c.get('temperature_2m')} °C, {desc}, "
            f"ощущается как {c.get('apparent_temperature')} °C, "
            f"влажность {c.get('relative_humidity_2m')} %, ветер {c.get('wind_speed_10m')} км/ч. "
            f"Время замера: {c.get('time')}."
        )
        WEATHER_CACHE[key] = (time.time(), text)
        return text
    except Exception as e:
        alt = _wttr_fallback(city)
        if alt:
            WEATHER_CACHE[key] = (time.time(), alt)
            return alt
        return (f"Сервис погоды недоступен ({type(e).__name__}). "
                f"Скажи пользователю об этом и предложи web_search.")


WORKSPACE = os.path.realpath(os.environ.get("WORKSPACE", "<AINE_HOME>/workspace"))


def _safe_path(path):
    p = os.path.realpath(os.path.join(WORKSPACE, str(path or ".").lstrip("/")))
    if p != WORKSPACE and not p.startswith(WORKSPACE + os.sep):
        raise ValueError(f"путь вне рабочей папки: {path}")
    return p


def tool_list_dir(path="."):
    p = _safe_path(path)
    if not os.path.isdir(p):
        return f"не каталог: {path}"
    items = sorted(os.listdir(p))[:200]
    marks = ["[d] " + i if os.path.isdir(os.path.join(p, i)) else "[f] " + i for i in items]
    return "\n".join(marks) or "(пусто)"


def tool_read_file(path, max_chars=6000):
    p = _safe_path(path)
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read(int(max_chars)) or "(пусто)"


def tool_write_file(path, content):
    p = _safe_path(path)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(str(content))
    return f"записано {len(str(content))} символов: {os.path.relpath(p, WORKSPACE)}"


def tool_run_command(command, timeout=60):
    r = subprocess.run(str(command), shell=True, cwd=WORKSPACE, capture_output=True,
                       text=True, timeout=min(int(timeout), 180))
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
    return f"exit={r.returncode}\n{out.strip()[:4000] or '(без вывода)'}"


def tool_git(args):
    r = subprocess.run(["git"] + str(args).split(), cwd=WORKSPACE, capture_output=True,
                       text=True, timeout=60)
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
    return f"exit={r.returncode}\n{out.strip()[:3000] or '(без вывода)'}"


def run_tool(name, args):
    try:
        if name == "web_search":
            return tool_web_search(args.get("query", ""))
        if name == "get_weather":
            return tool_get_weather(args.get("city", ""))
        if name == "list_dir":
            return tool_list_dir(args.get("path", "."))
        if name == "read_file":
            return tool_read_file(args.get("path", ""), args.get("max_chars", 6000))
        if name == "write_file":
            return tool_write_file(args.get("path", ""), args.get("content", ""))
        if name == "run_command":
            return tool_run_command(args.get("command", ""), args.get("timeout", 60))
        if name == "git":
            return tool_git(args.get("args", "status --short"))
        return f"Неизвестный инструмент: {name}"
    except Exception as e:
        return f"Ошибка инструмента {name}: {type(e).__name__}: {e}"


def call_upstream(messages, tools, model, max_tokens):
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        "temperature": 0.3,
        # Внутри агентного цикла размышления только тормозят: шаг занимает
        # 30-40 с вместо 2-3. Включается через AGENT_THINKING=1.
        "chat_template_kwargs": {"enable_thinking": THINKING},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return http_json(
        (FAST_URL if model == CHAT_MODEL else UPSTREAM) + "/v1/chat/completions",
        payload=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=900,
    )


AGENT_SYSTEM = (
    "Ты — агент на локальном сервере с инструментами (файлы, команды, git, поиск, погода).\n"
    "Правила:\n"
    "1. Если просят создать, сохранить или изменить файл/программу — ОБЯЗАТЕЛЬНО вызывай write_file. "
    "Не выводи весь код в чат: он не попадёт в файл и обрежется по лимиту.\n"
    "2. Если файл большой — записывай его частями (сначала write_file, затем дополняй через write_file с полным содержимым).\n"
    "3. После записи коротко скажи, что сохранено и по какому пути, и покажи не более 5 строк ключевого кода.\n"
    "4. Пути — относительные от рабочей папки, например calculator.py.\n"
    "5. Проверить результат можно через run_command (например, python3 calculator.py --help).\n"
    "6. Отвечай по-русски и кратко."
)


def run_agent(body):
    """Выполнить цикл «модель -> инструмент -> модель», вернуть (текст, источники)."""
    model = body.get("model", "")
    history = list(body.get("messages") or [])
    # У Qwen один system-месседж: если клиент (персона Open WebUI) уже прислал свой,
    # склеиваем с нашими правилами, иначе шаблон ломается и модель печатает tool_call текстом.
    client_system, rest = [], []
    for m in history:
        (client_system if m.get("role") == "system" else rest).append(m)
    merged = AGENT_SYSTEM
    for m in client_system:
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            merged += "\n\n---\n" + c.strip()
    messages = [{"role": "system", "content": merged}] + rest
    # Файл в аргументах tool-call — тоже completion-токены, поэтому лимит поднимаем
    max_tokens = max(int(body.get("max_tokens") or 0), 4096)
    tools = TOOLS
    used = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    # Память разума: до обращения к LLM ищем ответ в пыльце (резонанс)
    try:
        _last_user = next((m.get("content") for m in reversed(history)
                           if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
        if _last_user:
            _r = _resonate(_last_user)
            if _r:
                return ((_r.get("answer") or "").strip(),
                        [{"tool": "memory",
                          "title": "резонанс " + _r.get("archetype", "") + " (" + str(round(_r.get("resonance", 0), 2)) + ")"}],
                        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    except Exception:
        pass
    for _ in range(MAX_ROUNDS):
        data = call_upstream(messages, tools, model, max_tokens)
        _u = data.get("usage") or {}
        total_usage["prompt_tokens"] += _u.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += _u.get("completion_tokens", 0)
        total_usage["total_tokens"] += _u.get("total_tokens", 0)
        ch = (data.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text and msg.get("reasoning_content"):
                text = msg["reasoning_content"].strip()
            return text, used, total_usage
        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
        })
        for c in calls:
            fn = c.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(name, args)
            used.append({"tool": name, "args": args,
                         "title": args.get("query") or args.get("city") or name})
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
        tools = TOOLS  # на следующем шаге снова разрешаем инструменты
    # Шаги закончились, а итогового текста нет — просим короткое резюме без инструментов
    try:
        final = call_upstream(messages, [], model, 500)
        text = ((final.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        text = text.strip()
    except Exception:
        text = ""
    if not text:
        done = ", ".join(f"{u['tool']}({u['title']})" for u in used) or "без инструментов"
        text = f"Готово. Что сделано: {done}."
    # Саморефлексия: проверщик критикует, при «НЕТ» — улучшение
    if SELF_REFLECT and text:
        try:
            _lu = next((m.get("content") for m in reversed(history)
                        if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
            if _lu:
                _t2, _improved = self_reflect(_lu, text)
                if _improved:
                    text = _t2
                    used.append({"tool": "self_reflect", "title": "критика + улучшение"})
        except Exception:
            pass
    return text, used, total_usage


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _auth_ok(self):
        if not PROXY_TOKEN:
            return True
        got = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        return got == PROXY_TOKEN

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._json(200, {"status": "ok"})
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        if self.path.startswith("/v1/models"):
            try:
                data = http_json(UPSTREAM + "/v1/models",
                                 headers={"Authorization": f"Bearer {API_KEY}"})
                models = data.get("data") or []
                models.insert(0, {"id": "auto", "object": "model", "owned_by": "agent-proxy",
                                  "created": 0,
                                  "description": "Диспетчер: код → Coder, картинка → SD, фото → vision, текст → Qwen3.6"})
                data["data"] = models
                return self._json(200, data)
            except Exception as e:
                return self._json(502, {"error": str(e)})
        return self._json(404, {"error": "not found"})

    def _pipe_upstream(self, raw_body):
        """Прозрачная передача запроса в llama-server (без наших инструментов).

        Нужна для локальных агентов (Cline, Aider, Continue): инструменты они
        выполняют у себя на ПК, а сервер должен лишь отвечать моделью.
        """
        req = urllib.request.Request(
            UPSTREAM + "/v1/chat/completions", data=raw_body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {API_KEY}")
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=900)
        except urllib.error.HTTPError as e:
            raw = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        ctype = resp.headers.get("Content-Type", "application/json")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if "event-stream" in ctype:
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            self.close_connection = True
            return
        raw = resp.read()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        # трейсинг в Langfuse (не блокирует ответ)
        self._trace_langfuse(raw_body, raw, int((time.time() - t0) * 1000))

    def _trace_langfuse(self, raw_body, raw_resp, latency_ms):
        if not LANGFUSE_HOST:
            return
        def _send():
            try:
                try:
                    req_body = json.loads(raw_body.decode("utf-8", "replace") or "{}")
                except Exception:
                    req_body = {}
                try:
                    resp_body = json.loads(raw_resp.decode("utf-8", "replace") or "{}")
                except Exception:
                    resp_body = {}
                model = req_body.get("model", "")
                messages = req_body.get("messages", [])
                content = ""
                try:
                    content = resp_body["choices"][0]["message"]["content"]
                except Exception:
                    pass
                if not content:
                    return
                now_dt = datetime.now(timezone.utc)
                now = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                end = (now_dt + timedelta(milliseconds=latency_ms)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                u = resp_body.get("usage") or {}
                usage_lf = {"input": u.get("prompt_tokens", 0),
                            "output": u.get("completion_tokens", 0),
                            "total": u.get("total_tokens", 0)}
                tid = uuid.uuid4().hex
                gid = uuid.uuid4().hex
                batch = {"batch": [
                    {"id": f"t-{tid}", "type": "trace-create", "timestamp": now,
                     "body": {"id": tid, "name": model or "chat", "timestamp": now,
                              "input": messages, "output": content}},
                    {"id": f"g-{gid}", "type": "generation-create", "timestamp": now,
                     "body": {"id": gid, "traceId": tid, "name": "chat.completion",
                              "startTime": now, "endTime": end, "model": model,
                              "input": messages, "output": content,
                              "usage": usage_lf}},
                ]}
                req = urllib.request.Request(LANGFUSE_HOST + "/api/public/ingestion",
                                             data=json.dumps(batch).encode(), method="POST")
                req.add_header("Content-Type", "application/json")
                auth = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()
                req.add_header("Authorization", "Basic " + auth)
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._json(404, {"error": "not found"})
        if not self._auth_ok():
            return self._json(401, {"error": "unauthorized"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100 * 1024 * 1024:  # 100 MB limit
            return self._json(413, {"error": "payload too large"})
        raw = self.rfile.read(length)
        if not raw:
            return self._json(400, {"error": "empty request body"})
        if PASSTHROUGH:
            return self._pipe_upstream(raw)
        try:
            body = json.loads(raw.decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid JSON"})
        # Барьер постулатов (П8) + семантический для подозрительных запросов
        user_msg = ""
        _msgs = body.get("messages") or []
        if _msgs:
            user_msg = str(_msgs[-1].get("content", ""))
        allowed, why = barrier_check(user_msg)
        if not allowed:
            return self._json(200, {"id": "agent-proxy", "object": "chat.completion", "created": 0,
                "model": body.get("model", ""), "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": why}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        if re.search(r"напиши|удали|удалить|скрипт|команд|формат|выключи|перезагру|пароль|доступ|секрет", user_msg.lower()):
            bad, why2 = barrier_check_llm(user_msg, UPSTREAM, API_KEY)
            if bad:
                return self._json(200, {"id": "agent-proxy", "object": "chat.completion", "created": 0,
                    "model": body.get("model", ""), "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Барьер: " + why2}}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        stream = bool(body.get("stream"))
        t0 = time.time()
        try:
            with LLM_LOCK:
                text, used, usage = dispatch(body)
        except Exception as e:
            return self._json(502, {"error": f"{type(e).__name__}: {e}"})
        # трейсинг агентского пути (чат Open WebUI) в Langfuse — фоном
        self._trace_langfuse(raw, json.dumps(
            {"choices": [{"message": {"content": text}}], "usage": usage}).encode(),
            int((time.time() - t0) * 1000))
        sources = [{"title": u["title"], "url": "", "tool": u["tool"]} for u in used]
        if not stream:
            return self._json(200, {
                "id": "agent-proxy",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model", ""),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": usage,
                "sources": sources,
            })
        # Псевдо-стрим: отдаём готовый текст кусками, интерфейс это принимает
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        def send(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()
        if sources:
            send({"id": "agent-proxy", "sources": sources})
        step = 220
        for i in range(0, len(text), step):
            send({"id": "agent-proxy", "object": "chat.completion.chunk", "model": body.get("model", ""),
                  "choices": [{"index": 0, "delta": {"content": text[i:i + step]}, "finish_reason": None}]})
        send({"id": "agent-proxy", "object": "chat.completion.chunk", "model": body.get("model", ""),
              "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


if __name__ == "__main__":
    print(f"agent-proxy: :{PORT} -> {UPSTREAM}, поиск {SEARX}", flush=True)
    ThreadingHTTPServer((BIND_ADDR, PORT), Handler).serve_forever()

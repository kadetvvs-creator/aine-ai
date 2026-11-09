#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Саморазвитие AINE v5 — стратегия 12 путей + fuzzy-патч + версии + проверка влияния.

12 путей развития = 12 архетипов AINE. Движок оценивает пути, выбирает оптимальный,
при отказе предлагает альтернативный. Ничего НЕ применяет без одобрения человека.
"""
import sys, os, json, time, subprocess, hashlib, re, urllib.request

ORGAN = "http://127.0.0.1:8080/v1/chat/completions"
KEY = "5yicZ3KPrbRePFaxJvl7MV5D6FNofoBD"
PROPOSALS = "/home/aine/workspace/aine/proposals"
STATE = "/home/aine/workspace/aine/selfdev_state.json"
SETTINGS = "/home/aine/workspace/aine/selfdev_settings.json"
SELFDEV_DEFAULTS = {
    "model": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",
    "mode": "auto",       # auto | fix | feature
    "confidence": 0.7,    # порог уверенности
    "rounds": 3,          # раундов рефлексии
    "interval_h": 3,      # период таймера
}


def load_settings():
    try:
        return {**SELFDEV_DEFAULTS, **json.load(open(SETTINGS, encoding="utf-8"))}
    except Exception:
        return dict(SELFDEV_DEFAULTS)

FILES = {
    "proxy.py": "/opt/agent-proxy/proxy.py",
    "dashboard.py": "/home/aine/workspace/dashboard/dashboard.py",
    "ail.py": "/home/aine/vokivon/aine/ail.py",
}

# 12 путей развития = 12 архетипов
PATHS = ["наблюдатель", "страж", "собиратель", "аналитик", "координатор", "исполнитель",
         "связник", "хранитель", "обучатель", "проверщик", "строитель", "прорицатель"]


def ask(prompt, model=None, max_tokens=3000):
    model = model or load_settings()["model"]
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.2,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(ORGAN, data=body,
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return (r["choices"][0]["message"].get("content") or "")


def _json_of(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0), strict=False)
    except Exception:
        return {}


def _code_of(text):
    m = re.search(r"```(?:python|py)?\s*\n?(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"level": 1, "proposals": 0, "approved": 0, "paths": {}}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ── Fuzzy-применение патча ──────────────────────────────────────────
def _fuzzy_apply(src, old, new):
    if old in src:
        return src.replace(old, new, 1), True
    # построчный fuzzy (strip каждой строки)
    old_lines = [l.strip() for l in old.split("\n") if l.strip()]
    src_lines = src.split("\n")
    for i in range(len(src_lines) - len(old_lines) + 1):
        if [l.strip() for l in src_lines[i:i + len(old_lines)]] == old_lines:
            head = "\n".join(src_lines[:i])
            tail = "\n".join(src_lines[i + len(old_lines):])
            return (head + ("\n" if head else "") + new + ("\n" if tail else "") + tail), True
    return src, False


def apply_edits(src, edits):
    for e in edits:
        old = e.get("old", "")
        new = e.get("new", "")
        if not old:
            return None, "пустой old"
        src, ok = _fuzzy_apply(src, old, new)
        if not ok:
            return None, "old не найден: " + old[:80]
    return src, ""


# ── Стратегия 12 путей ─────────────────────────────────────────────
def _fetch_concepts():
    """Новые знания: понятия генома (кластеры пыльцы)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8091/api/aine/concepts")
        r = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return [c.get("label", "") for c in r.get("concepts", [])][:10]
    except Exception:
        return []


def mutate_strategy(st):
    """Мутация стратегии: обновить веса путей и добавить новые пути из знаний."""
    concepts = _fetch_concepts()
    prompt = ("Ты — стратег саморазвития AINE. Текущая стратегия (JSON): " + json.dumps(st, ensure_ascii=False) + ". "
              "Новые знания из интернет-парсинга и понятий генома: " + ", ".join(concepts) + ". "
              "Предложи МУТАЦИЮ: обнови веса путей (успех → выше, провал → ниже), добавь новые пути из знаний. "
              "Верни JSON: {\"weights\": {\"путь\": вес}, \"new_paths\": [...], \"reason\": \"почему\"}")
    d = _json_of(ask(prompt))
    if d.get("weights"):
        st["weights"] = d["weights"]
    for p in (d.get("new_paths") or []):
        st.setdefault("paths", {})
        st["paths"].setdefault(p, 0)
    st["mutations"] = st.get("mutations", [])
    st["mutations"].append({"ts": time.time(), "reason": d.get("reason", ""),
                            "weights": st.get("weights", {})})
    save_state(st)
    return st


def evaluate_paths():
    st = load_state()
    failures = st.get("failures", {})
    weights = st.get("weights", {})
    fail_str = (", ".join(f"{k}: {v} провал(ов)" for k, v in failures.items())
                if failures else "провалов пока нет")
    w_str = (", ".join(f"{k}={v}" for k, v in weights.items()) if weights else "веса ещё не мутировали")
    prompt = ("Ты — стратег саморазвития AINE. Базовые пути: " + ", ".join(PATHS) + ". "
              "Текущие веса (после мутаций): " + w_str + ". "
              "Провалы (ниже приоритет): " + fail_str + ". "
              "Оцени пути по ценности (1-10) и риску (1-10), учитывая веса и провалы. "
              "Верни JSON: {\"optimal\": \"путь\", \"reason\": \"почему\", "
              "\"alternatives\": [\"путь2\", \"путь3\"]}")
    d = _json_of(ask(prompt))
    return d.get("optimal", "проверщик"), d


def analyze(path):
    """Конкретная самодиагностика по выбранному пути развития."""
    names = ", ".join(FILES.keys())
    prompt = ("Ты — инженер AINE. Проанализируй активный код (" + names + ") С ФОКУСОМ на путь: " + path + ". "
              "Найди ОДНО конкретное слабое место, связанное с этим путём. "
              "Верни JSON: {\"file\": \"имя\", \"type\": \"fix\"|\"feature\", "
              "\"weakness\": \"конкретное слабое место\", \"critique\": \"почему важно\", "
              "\"fix\": \"что точечно изменить\", \"feature\": \"описание новой функции\"}")
    d = _json_of(ask(prompt))
    d.setdefault("file", "ail.py")
    d.setdefault("type", "fix")
    return d


def propose(info, path):
    name = info.get("file", "ail.py")
    cur = open(FILES.get(name, FILES["ail.py"]), encoding="utf-8").read()
    typ = info.get("type", "fix")
    mode = load_settings().get("mode", "auto")
    if mode == "feature":
        typ = "feature"
    elif mode == "fix":
        typ = "fix"
    if typ == "feature":
        code = _code_of(ask("Напиши новую компактную функцию/модуль Python (путь развития: " + path +
                            "). ТОЛЬКО код в ```python с self-test в if __name__."))
        if not code:
            return None, "нет кода"
        tmp = "/tmp/aine_feature_test.py"
        open(tmp, "w", encoding="utf-8").write(code)
        r = subprocess.run([sys.executable, "-m", "py_compile", tmp], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None, "синтаксис: " + r.stderr[-300:]
        return {"feature_code": code}, ""
    # fix: патч
    prompt = ("Исправь точечно (путь: " + path + "). Верни JSON {\"edits\": [{\"old\":\"фрагмент\",\"new\":\"замена\"}]}. "
              "old — это ТОЧНАЯ копия 1-3 строк из кода ниже (символ в символ, с отступами), НЕ описание и НЕ пересказ.\\nФайл: " + name +
              "\\nСлабость: " + info.get("weakness", "") + "\\nФикс: " + info.get("fix", "") + "\\n\\nКод:\\n" + cur)
    edits = _json_of(ask(prompt)).get("edits", [])
    if not edits:
        return None, "нет правок"
    src, err = apply_edits(cur, edits)
    if err:
        return None, err
    tmp = "/tmp/aine_proposal_test.py"
    open(tmp, "w", encoding="utf-8").write(src)
    r = subprocess.run([sys.executable, "-m", "py_compile", tmp], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None, "синтаксис: " + r.stderr[-300:]
    return {"edits": edits}, ""


def reflect_and_refine(info, path, rounds=None, confidence=None):
    """Рефлексивный цикл: тест → обдумывание → переосмысление → до уверенности."""
    cfg = load_settings()
    rounds = rounds or cfg["rounds"]
    confidence = cfg["confidence"] if confidence is None else confidence
    result, err = propose(info, path)
    if result is None:
        return None, False, err
    for rnd in range(rounds):
        review = ask("Ты — строгий проверщик AINE. Оцени предложение (путь: " + path + "). "
                     "Верно ли решает проблему? Есть ли риск сломать систему? Есть ли лучшее решение? "
                     "Верни строго JSON: {\"good\": true/false, \"confidence\": 0..1, \"why\": \"причина\"}")
        d = _json_of(review)
        if d.get("good") and d.get("confidence", 0) >= confidence:
            return result, True, ""
        info2 = dict(info)
        info2["fix"] = ("Улучши предложение с учётом критики: " + d.get("why", "") +
                        " (путь: " + path + ")")
        result, err = propose(info2, path)
        if result is None:
            return None, False, err
    return result, False, "не достиг уверенности после " + str(rounds) + " раундов"


def run():
    st = load_state()
    if st.get("proposals", 0) > 0 and st.get("proposals", 0) % 5 == 0:
        st = mutate_strategy(st)
    optimal, strat = evaluate_paths()
    info = analyze(optimal)
    info["critique"] = info.get("critique", "") + " (путь: " + optimal + ")"
    result, confident, err = reflect_and_refine(info, optimal)
    if not confident:
        # ветвление: альтернативный путь (если первый не дал уверенности)
        for alt in strat.get("alternatives", []):
            result, confident, err = reflect_and_refine(dict(info, fix="улучшить путь " + alt), alt)
            if confident:
                optimal = alt
                break
    if not confident:
        return {"status": "skipped", "reason": err, "path": optimal}
    pid = hashlib.md5((optimal + str(time.time())).encode()).hexdigest()[:10]
    proposal = {"id": pid, "ts": time.time(), "status": "pending", "level": st.get("level", 1),
                "path": optimal, "type": info.get("type"), "file": info.get("file"),
                "weakness": info.get("weakness"), "critique": info.get("critique"),
                "strategy": strat.get("reason", ""), **result, "tested": True}
    os.makedirs(PROPOSALS, exist_ok=True)
    json.dump(proposal, open(os.path.join(PROPOSALS, pid + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    st["proposals"] = st.get("proposals", 0) + 1
    st["paths"][optimal] = st["paths"].get(optimal, 0) + 1
    save_state(st)
    return {"status": "proposed", "id": pid, "path": optimal, "type": info.get("type")}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))

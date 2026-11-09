#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AINE · авто-парсинг интернета (web_learn) v3.

Новое: настройки (вкл/выкл, загрузка при простое, тренды, дедуп) + лог прогонов.
"""
import requests, sys, os, json, time

AIL_DIR = "<AINE_HOME>/vokivon/aine"
GENOME = "<AINE_HOME>/workspace/aine/ail/genome.json"
SEARX = "http://127.0.0.1:8088"
EMBED = "http://127.0.0.1:8084/v1/embeddings"
EMBED_KEY = os.environ.get("LLAMA_API_KEY", "")
EMBED_CACHE = "<AINE_HOME>/workspace/aine/ail/web_learn_embeds.json"
LEARN_SETTINGS = "<AINE_HOME>/workspace/documents/state/learn.json"
LEARN_LOG = "<AINE_HOME>/workspace/documents/state/learn_log.json"
DEDUP_THRESHOLD = 0.88

TOPICS = [
    ("искусственный интеллект новости", "собиратель"),
    ("экономика и финансы России", "аналитик"),
    ("новые технологии производство", "строитель"),
    ("кибербезопасность и защита данных", "страж"),
    ("управление персоналом и кадры", "координатор"),
    ("контроль качества и аудит", "проверщик"),
    ("стратегические прогнозы и тренды", "прорицатель"),
    ("энергетика и промышленность", "строитель"),
    ("медицина и здоровье", "хранитель"),
    ("образование и обучение", "обучатель"),
    ("логистика и транспорт", "координатор"),
    ("наука и открытия", "собиратель"),
]


def _load_settings():
    d = {"enabled": True, "idle_max": 50, "trends": True, "dedup": True}
    try:
        d.update(json.load(open(LEARN_SETTINGS, encoding="utf-8")))
    except Exception:
        pass
    return d


def _idle_pct():
    """Текущая загрузка CPU в % (load1 / ядра * 100)."""
    try:
        load1 = float(open("/proc/loadavg").read().split()[0])
        cores = os.cpu_count() or 16
        return round(load1 / cores * 100, 1)
    except Exception:
        return 0.0


def _load_ail():
    import importlib.util
    spec = importlib.util.spec_from_file_location("aine_ail", AIL_DIR + "/ail.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aine_ail"] = mod
    spec.loader.exec_module(mod)
    return mod.AineAilEngine(GENOME)


def _embed(text):
    try:
        r = requests.post(EMBED, headers={"Authorization": "Bearer " + EMBED_KEY,
                                          "Content-Type": "application/json"},
                          json={"model": "nomic-embed-text-v1.5", "input": text[:1500]}, timeout=40)
        return r.json()["data"][0]["embedding"]
    except Exception:
        return None


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _load_cache():
    try:
        return json.load(open(EMBED_CACHE, encoding="utf-8"))
    except Exception:
        return []


def _save_cache(c):
    os.makedirs(os.path.dirname(EMBED_CACHE), exist_ok=True)
    json.dump(c, open(EMBED_CACHE, "w", encoding="utf-8"), ensure_ascii=False)


def _is_dup(emb, cache):
    for e in cache[-300:]:
        if _cosine(emb, e) > DEDUP_THRESHOLD:
            return True
    return False


def _trending_topics():
    out = []
    try:
        r = requests.get(SEARX + "/search",
                         params={"q": "новости сегодня главное", "format": "json", "language": "ru"},
                         timeout=25)
        for res in r.json().get("results", [])[:8]:
            t = (res.get("title") or "").strip()
            if len(t) > 6:
                out.append((t[:120], "собиратель"))
    except Exception:
        pass
    return out


def _log_run(added, topics_n, skipped):
    try:
        log = json.load(open(LEARN_LOG, encoding="utf-8")) if os.path.exists(LEARN_LOG) else []
    except Exception:
        log = []
    log.append({"ts": time.time(), "added": added, "topics": topics_n,
                "skipped": skipped, "load": _idle_pct()})
    os.makedirs(os.path.dirname(LEARN_LOG), exist_ok=True)
    json.dump(log[-60:], open(LEARN_LOG, "w", encoding="utf-8"), ensure_ascii=False)


def web_learn(max_per_topic=4):
    st = _load_settings()
    if not st.get("enabled", True):
        print("web_learn: выключено настройками")
        return 0
    load = _idle_pct()
    if load > st.get("idle_max", 50):
        print(f"web_learn: сервер занят (load {load}% > {st.get('idle_max')}%) — пропуск")
        _log_run(0, 0, skipped=1)
        return 0

    engine = _load_ail()
    cache = _load_cache()
    added = 0
    topics = TOPICS + (_trending_topics() if st.get("trends", True) else [])
    for topic, arch in topics:
        try:
            r = requests.get(SEARX + "/search",
                             params={"q": topic, "format": "json", "language": "ru"}, timeout=25)
            for res in r.json().get("results", [])[:max_per_topic]:
                title = (res.get("title") or "").strip()[:120]
                snippet = (res.get("content") or res.get("snippet") or "").strip()[:400]
                if not (title and snippet):
                    continue
                text = f"{title}. {snippet}"
                emb = _embed(text) if st.get("dedup", True) else None
                if emb is not None:
                    if _is_dup(emb, cache):
                        continue
                    cache.append(emb)
                engine.add_pollen(arch, topic[:120], text, origin="learned")
                added += 1
        except Exception as e:
            print(f"  ! {topic}: {type(e).__name__}")
    _save_cache(cache[-400:])
    engine.save()
    _log_run(added, len(topics), skipped=0)
    return added


if __name__ == "__main__":
    n = web_learn()
    print(f"web_learn v3: +{n} пыльцы")

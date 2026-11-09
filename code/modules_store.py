#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AINE Library — формат модуля и локальное хранилище (этап 1)."""
import json, os, time, hashlib

MODULES_DIR = "<AINE_HOME>/workspace/aine/modules"


def _dir(store):
    d = os.path.join(MODULES_DIR, store)
    os.makedirs(d, exist_ok=True)
    return d


def new_module(code, name, preview, confidence, author, typ="feature", edits=None):
    """Создать модуль в едином формате AINE Library."""
    mid = hashlib.sha256((code or json.dumps(edits or [])).encode()).hexdigest()[:12]
    m = {
        "id": mid, "type": typ, "name": name, "preview": preview,
        "confidence": round(float(confidence or 0), 3), "tested": True,
        "author": author, "version": "1.0.0", "tags": [], "rating": 0,
        "deps": {"aine": ">=1.0"}, "created_at": time.time(), "downloads": 0, "verified": False,
    }
    if typ == "feature":
        m["code"] = code
    else:
        m["edits"] = edits or []
    return m


def save_module(m, store="my"):
    """Сохранить модуль в локальное хранилище (my — свои, pulled — чужие)."""
    json.dump(m, open(os.path.join(_dir(store), m["id"] + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return m["id"]


def list_modules(store="my"):
    """Список модулей из хранилища."""
    d = os.path.join(MODULES_DIR, store)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            try:
                out.append(json.load(open(os.path.join(d, fn), encoding="utf-8")))
            except Exception:
                pass
    return out


def module_preview(code, name, ask):
    """AINE пишет превью для модуля (что делает, зачем, как использовать)."""
    try:
        p = ask("Напиши короткое превью (2-3 предложения) для модуля «" + name + "»: "
                "что он делает, зачем полезен, как использовать. Без кода.\nКод:\n" + (code or "")[:1500],
                max_tokens=120)
        return (p or "").strip()
    except Exception:
        return ""


LIBRARY_REPO = os.environ.get("AINE_LIBRARY_REPO", "https://github.com/kadetvvs-creator/aine-library.git")


def _repo_sync():
    """Клонировать/обновить локальную копию библиотеки."""
    import subprocess
    local = os.path.expanduser("~/.aine-library")
    if os.path.isdir(os.path.join(local, ".git")):
        subprocess.run(["git", "-C", local, "pull", "--rebase"], capture_output=True, text=True, timeout=120)
    else:
        subprocess.run(["git", "clone", LIBRARY_REPO, local], capture_output=True, text=True, timeout=180)
    return local


def github_publish(m):
    """Опубликовать модуль в общую библиотеку (GitHub)."""
    import subprocess
    local = _repo_sync()
    fp = os.path.join(local, "modules", m["id"] + ".json")
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    json.dump(m, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    subprocess.run(["git", "-C", local, "add", "."], capture_output=True)
    subprocess.run(["git", "-C", local, "-c", "user.name=AINE", "-c", "user.email=aine@local",
                    "commit", "-m", "module: " + m.get("name", m["id"])], capture_output=True)
    r = subprocess.run(["git", "-C", local, "push"], capture_output=True, text=True, timeout=180)
    return m["id"], (r.returncode == 0)


def github_pull():
    """Подтянуть модули из общей библиотеки (GitHub)."""
    local = _repo_sync()
    d = os.path.join(local, "modules")
    out = []
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.endswith(".json"):
                try:
                    out.append(json.load(open(os.path.join(d, fn), encoding="utf-8")))
                except Exception:
                    pass
    return out


def _embed(preview):
    """Эмбеддинг превью (BGE-M3) для семантического поиска."""
    try:
        import sys
        sys.path.append("<AINE_HOME>/vokivon/aine")
        from ail import _embed_text
        return _embed_text(preview or "")
    except Exception:
        return None


def embed_module(m):
    """Добавить эмбеддинг превью модулю (если нет)."""
    if not m.get("embedding"):
        m["embedding"] = _embed(m.get("preview", ""))
    return m


def semantic_search(q, mods):
    """Семантический поиск: эмбеддинг запроса × эмбеддинг превью."""
    try:
        import sys
        sys.path.append("<AINE_HOME>/vokivon/aine")
        from ail import _embed_text, _cosine
        q_emb = _embed_text(q or "")
        scored = []
        for m in mods:
            emb = m.get("embedding") or _embed(m.get("preview", ""))
            if emb:
                scored.append((_cosine(q_emb, emb), m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored]
    except Exception:
        return []


def aine_profile():
    """Профиль конкретной AINE: уровень, пути, провалы, наполненность архетипов."""
    import json
    arch = {}
    try:
        import sys
        sys.path.append("<AINE_HOME>/vokivon/aine")
        from ail import AineAilEngine
        e = AineAilEngine("<AINE_HOME>/workspace/aine/ail/genome.json")
        e.load()
        arch = {a.archetype: len(a.pollen) for a in e.agents.values()}
    except Exception:
        pass
    try:
        st = json.load(open("<AINE_HOME>/workspace/aine/selfdev_state.json", encoding="utf-8"))
    except Exception:
        st = {}
    return {"level": st.get("level", 1), "paths": st.get("paths", {}),
            "failures": st.get("failures", {}), "archetypes": arch,
            "pollen_total": sum(arch.values())}


def recommend(profile, mods, limit=5):
    """Рекомендации: модули, закрывающие пробелы ИМЕННО этой AINE."""
    gaps = []
    for a, n in profile.get("archetypes", {}).items():
        if n < 3:            # слабо развитый архетип
            gaps.append(a)
    for p in profile.get("failures", {}):
        gaps.append(p.split("/")[-1])   # файл с провалами
    scored = []
    for m in mods:
        text = (m.get("name", "") + " " + m.get("preview", "") + " " +
                " ".join(m.get("tags", []))).lower()
        score = sum(1 for g in gaps if g.lower() in text)
        score += m.get("rating", 0) * 0.1
        score += m.get("downloads", 0) * 0.01
        if score > 0:
            scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]], gaps

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
P = "<AINE_HOME>/modules_store.py"
s = open(P, encoding="utf-8").read()

add = '''

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
'''
assert add not in s, "already added"
s += add
open(P, "w", encoding="utf-8").write(s)
import ast
ast.parse(open(P, encoding="utf-8").read())
print("modules_store.py: профиль AINE + рекомендации добавлены")

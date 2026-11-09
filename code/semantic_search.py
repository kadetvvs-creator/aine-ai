#!/usr/bin/env python3
# -*- coding: utf-8 -*-
P = "<AINE_HOME>/modules_store.py"
s = open(P, encoding="utf-8").read()

# 1) downloads в new_module
s = s.replace('"deps": {"aine": ">=1.0"}, "created_at": time.time(),',
              '"deps": {"aine": ">=1.0"}, "created_at": time.time(), "downloads": 0, "verified": False,')

# 2) эмбеддинг + семантический поиск (в конец файла)
add = '''

def _embed(preview):
    """Эмбеддинг превью (nomic-embed) для семантического поиска."""
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
'''
assert add not in s, "already added"
s += add
open(P, "w", encoding="utf-8").write(s)
import ast
ast.parse(open(P, encoding="utf-8").read())
print("modules_store.py: downloads + эмбеддинг + семантический поиск добавлены")

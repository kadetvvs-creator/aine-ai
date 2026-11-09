#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Чистка генома: удалить мусор (запросы пользователя, сырые заголовки новостей)."""
import sys
sys.path.append("<AINE_HOME>/vokivon/aine")
from ail import AineAilEngine

G = "<AINE_HOME>/workspace/aine/ail/genome.json"
e = AineAilEngine(G)
e.load()

JUNK = [
    "привет",
    "изучи прикрепленный файл",
    "пожалуйста, изучи",
    "рамбер",
    "российская газета",
    "последние новости",
    "новости россии и мира",
    "свежие новости",
    "лента.ру",
    "рбк",
    "тасс",
    "риа новости",
]

before = sum(len(a.pollen) for a in e.agents.values())
removed = 0
for agent in e.agents.values():
    kept = []
    for p in agent.pollen:
        cond = (p.condition or "").lower()
        if any(j in cond for j in JUNK):
            removed += 1
        else:
            kept.append(p)
    agent.pollen = kept

e.save()
after = sum(len(a.pollen) for a in e.agents.values())
print(f"пыльца: {before} → {after} (удалено {removed})")

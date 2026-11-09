#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Бенчмарк v2: по ФАКТИЧЕСКИМ условиям пыльцы (точные/парафраз/чужие)."""
import sys
sys.path.append("<AINE_HOME>/vokivon/aine")
from ail import AineAilEngine

G = "<AINE_HOME>/workspace/aine/ail/genome.json"
e = AineAilEngine(G)
e.load()

QUESTIONS = [
    # точные условия (должны попадать в память)
    ("стратегические прогнозы и тренды", "exact"),
    ("экономика и финансы России", "exact"),
    ("наука и открытия", "exact"),
    ("искусственный интеллект новости", "exact"),
    # парафразы (должны попадать)
    ("какие тренды и прогнозы будут в 2026", "paraphrase"),
    ("что происходит с экономикой в россии", "paraphrase"),
    ("последние открытия в науке", "paraphrase"),
    ("новости про искусственный интеллект", "paraphrase"),
    # чужие (должны уходить в LLM)
    ("столица франции", "unrelated"),
    ("сколько будет 2+2", "unrelated"),
    ("кто написал войну и мир", "unrelated"),
]

hits = {"exact": 0, "paraphrase": 0, "unrelated": 0}
totals = {"exact": 0, "paraphrase": 0, "unrelated": 0}
print("=== бенчмарк v2 (фактические условия) ===")
for q, kind in QUESTIONS:
    totals[kind] += 1
    r = e.resonate(q)
    hit = r and r.get("resonance", 0) >= 0.35
    if hit:
        hits[kind] += 1
    mark = "✅ память" if hit else "⏳ LLM"
    print(f"  {mark} [{kind:10}] {q[:45]}")

print("\n=== ИТОГ ===")
for k in ("exact", "paraphrase", "unrelated"):
    print(f"  {k}: {hits[k]}/{totals[k]} = {hits[k]/totals[k]*100 if totals[k] else 0:.0f}%")

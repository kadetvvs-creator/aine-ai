#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Бенчмарк живой памяти AINE: покрытие, задержка, экономия токенов."""
import sys, time, json, urllib.request
sys.path.append("<AINE_HOME>/vokivon/aine")
from ail import AineAilEngine

G = "<AINE_HOME>/workspace/aine/ail/genome.json"
ORG = "http://127.0.0.1:8080/v1/chat/completions"
KEY = os.environ.get("LLAMA_API_KEY", "")

QUESTIONS = [
    ("стратегические прогнозы и тренды", "memory"),
    ("что такое кибербезопасность", "memory"),
    ("управление персоналом и кадры", "memory"),
    ("контроль качества и аудит", "memory"),
    ("новые технологии в производстве", "memory"),
    ("экономика и финансы россии", "memory"),
    ("медицина и здоровье", "memory"),
    ("образование и обучение", "memory"),
    ("энергетика и промышленность", "memory"),
    ("логистика и транспорт", "memory"),
    ("сколько будет 2+2", "non-memory"),
    ("столица франции", "non-memory"),
    ("кто написал войну и мир", "non-memory"),
    ("какая валюта в японии", "non-memory"),
    ("привет как дела", "non-memory"),
]


def llm_call(q):
    t0 = time.time()
    body = json.dumps({"model": "Qwen3.6-35B-A3B-UD-Q4_K_M",
                       "messages": [{"role": "user", "content": q}],
                       "max_tokens": 30,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(ORG, data=body,
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return time.time() - t0, r.get("usage", {}).get("total_tokens", 0)


def main():
    e = AineAilEngine(G)
    e.load()
    hits = 0
    mem_ms = []
    llm_s = []
    tokens = []
    print("=== бенчмарк живой памяти ===")
    for q, kind in QUESTIONS:
        t0 = time.time()
        r = e.resonate(q)
        t_mem = time.time() - t0
        if r and r.get("resonance", 0) >= 0.35:
            hits += 1
            mem_ms.append(t_mem * 1000)
            print(f"  ✅ память  {q[:38]:<38} {t_mem*1000:7.0f} мс")
        else:
            lt, tk = llm_call(q)
            llm_s.append(lt)
            tokens.append(tk)
            print(f"  ⏳ LLM     {q[:38]:<38} {lt:6.1f} с ({tk} токенов)")

    n = len(QUESTIONS)
    coverage = hits / n * 100
    avg_mem = (sum(mem_ms) / len(mem_ms)) if mem_ms else 0
    avg_llm = (sum(llm_s) / len(llm_s)) if llm_s else 0
    avg_tok = (sum(tokens) / len(tokens)) if tokens else 0
    print("\n=== ИТОГ ===")
    print(f"  покрытие памяти: {hits}/{n} = {coverage:.0f}%")
    print(f"  средняя задержка: память {avg_mem:.0f} мс | LLM {avg_llm:.1f} с")
    print(f"  экономия: в {avg_llm/(avg_mem/1000) if avg_mem else 0:.0f} раз быстрее")
    print(f"  токены LLM на ответ: {avg_tok:.0f} (память = 0 токенов)")
    print(f"  сэкономлено токенов на {hits} ответах: ~{hits * avg_tok:.0f}")


if __name__ == "__main__":
    main()

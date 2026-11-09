# AINE — A Living, Self-Improving AI

**A local, autonomous, human-controlled AI system with evolutionary memory.**

AINE is not a "wrapper over an LLM" — it is a three-layer organism that **remembers, generalizes, critiques itself, evolves, and writes its own improvements** — fully locally on your hardware, under human control.

---

## 🧬 Architecture: three layers

```
LAYER 1: GENOME (personality/memory) ← 12 archetypes, pollen "condition→response", evolution
        │ resonance (Jaccard retrieval)
LAYER 2: ORGAN (brain)               ← local LLMs (Qwen/Gemma, llama.cpp)
        │ tasks
LAYER 3: BODY (execution)            ← tools: files, code, search, weather
```

**Core principle:** the personality (genome) survives a brain swap; the brain can be upgraded without touching the personality.

## ✨ Key capabilities

| Capability | Description |
|---|---|
| 🧠 **Evolutionary memory** | pollen → concepts → rules; strength grows with use, weak decays |
| 🔄 **Self-reflection** | generate → critique → refine (until confident) |
| 🎯 **Self-engineering** | AINE writes its own code, tests, debugs, proposes |
| 🧩 **12-path strategy** | 12 development archetypes; mutates, learns from failures |
| 🛡️ **Fault tolerance** | versioning + impact check + auto-rollback |
| 👤 **Human control** | veto, kill-switch, 👍/👎, approval of every change |

## 📊 Proven efficiency (benchmark)

| Metric | Result |
|---|---|
| Memory speedup | **89×** (14 ms vs 1.3 s) |
| Token savings | **100%** (0 vs 42) |
| Accuracy | **100%** (0 false positives) |
| Coverage | 40% (grows with accumulation) |

*Full benchmark: `docs/en/AINE_benchmark_report.md`*

## 📐 Formal model

Resonance, strength evolution, concepts and rules are described mathematically — see `docs/en/AINE_formal_model.md`.

## 🚀 Quick start

```bash
# 1. models (llama.cpp)
llama-server --models-dir /var/lib/llama/models -c 32768 -t 8 -ngl 99

# 2. embeddings
llama-server -m nomic-embed-text-v1.5.gguf --port 8084

# 3. AINE engine (genome + memory)
python3 self_improve.py   # self-development
python3 benchmark.py       # memory benchmark
```

Full deployment: `docs/aine_full_deployment_doc.md`

## 📚 Documentation

- [`docs/AINE_status_report.md`](docs/AINE_status_report.md) — system status (RU);
- [`docs/en/AINE_benchmark_report.md`](docs/en/AINE_benchmark_report.md) — measurements (EN);
- [`docs/en/AINE_formal_model.md`](docs/en/AINE_formal_model.md) — mathematics (EN);
- [`docs/en/AINE_redteam_report.md`](docs/en/AINE_redteam_report.md) — safety (EN).

## 🛡️ Safety and control

- **Postulates barrier** — filters knowledge and actions;
- **Veto right** — interrupt any autonomous step;
- **Kill-switch** — instant stop;
- **Human approval** — every change is confirmed.

## 📜 License

MIT — see [LICENSE](LICENSE).

---

*AINE is the "Linux moment" for AI: your own, living, controlled mind on your hardware.*

# AINE — Full Deployment (EN summary)

**Server:** `<server-ip>` (Ubuntu, 8 cores/16 threads CPU, 62 GB RAM, Radeon 780M iGPU + 48 GB GTT).

> This is the English summary of the full Russian deployment document. For complete details see `aine_full_deployment_doc.md` (RU).

---

## 1. Architecture (three layers)

```
GENOME (personality/memory)  — 12 archetypes, pollen "condition→response", evolution
ORGAN (brain)                — local LLMs via llama.cpp (Qwen/Gemma)
BODY (execution)             — tools + systemd services + dashboard
```

## 2. Components

| Component | Where | Role |
|---|---|---|
| llama-server | :8080 | organ (LLM) |
| llama-fast | :8095 | voice (fast model) |
| agent-proxy-lan | :8086 | agent + resonance + orchestration |
| llama-embed | :8084 | embeddings (nomic-embed, 768-dim) |
| dashboard | :8091 | cabinet + all AINE APIs |
| aine-mcp | :8100 | MCP tools |
| watcher | :8093 | autonomous loop |
| nginx | 80/443 | reverse proxy |

## 3. Directory layout

```
<AINE_HOME>/workspace/dashboard/   — cabinet
<AINE_HOME>/workspace/aine/        — genome + state + proposals
<AINE_HOME>/vokivon/               — AINE Python code (ail.py)
<INSTALL>/agent-proxy/             — agent proxy (proxy.py)
```

## 4. Quick start

```bash
# 1. models
llama-server --models-dir /var/lib/llama/models -c 32768 -t 8 -ngl 99

# 2. embeddings
llama-server -m nomic-embed-text-v1.5.gguf --port 8084

# 3. engine
python3 self_improve.py    # self-development
python3 benchmark.py       # memory benchmark

# or everything at once:
docker compose up --build  # see docker/
```

## 5. Autonomy timers (systemd)

| Timer | Interval | Role |
|---|---|---|
| aine-learn | 4h | web learning (internet → pollen) |
| aine-evolve | 1h | genome evolution (decay + infection) |
| aine-selfimprove | 3h | self-development (analyze → fix → propose) |

## 6. Safety layers

1. **Postulates barrier** — blocks forbidden actions (`rm -rf`, `passwd`, `shutdown`…).
2. **Veto** — human approval of every autonomous change.
3. **Kill-switch** — instant stop.
4. **Auto-rollback** — impact check + versioning before applying.

---

*See `docker/docker-compose.yml` for the one-command setup.*

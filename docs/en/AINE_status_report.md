# AINE — System Status Report (current)

**Date:** 09.11.2026
**Server:** `<server-ip>` (Ubuntu, 8 cores/16 threads, 62 GB RAM, Radeon 780M iGPU + 48 GB GTT)
**Status:** all services and features verified with live tests after a full rework cycle
**Base document:** [`aine_full_deployment_doc.md`](aine_full_deployment_doc.md) (architecture and history)

---

## 1. One-paragraph summary

AINE is a **three-layer bio-inspired system** (genome/organ/body) on local LLMs,
to which four new "pillars" of self-improvement were added in the current cycle:

1. **Genome 2.0** — semantic resonance (embeddings instead of substring);
2. **Self-reflection** — generate → critique → improve;
3. **Neuro-symbolic layer** — "if → then" rules with confidence;
4. **Orchestration** — voice 8B / organ 35B / tools.

Result: AINE moved from "memory + LLM" to a **living self-improving system**, fully local.

---

## 2. Three layers (architecture)

```
LAYER 1: GENOME (personality/memory)  ← 12 archetypes, 161 pollen (all with embeddings)
        │ resonance (semantic)
LAYER 2: ORGAN (brain on call)        ← Qwen3.6-35B / Qwen3-Coder-30B / Gemma-26B / Qwen3.8-27B
        │ tasks
LAYER 3: BODY (execution)             ← tools (files/code/search/weather) + services
```

**Core principle:** the personality (genome) survives a brain swap; the brain can be upgraded without touching the personality.

---

## 3. Four pillars of the "breakthrough" (implemented)

### 3.1. Genome 2.0 — semantic memory
- **Was:** resonance = substring (`cond in req`) — almost never triggered.
- **Now:** query embedding × pollen embedding → cosine → resonance.
- **Backfill:** all 161 pollen enriched with embeddings (nomic-embed, 768 dim).
- Verified: paraphrase "which directions will grow" → found "strategic forecasts" (0.53).

### 3.2. Self-reflection
- After generation, a "critic" reviews (YES/NO + why).
- On "NO" — improvement using the critique.
- Enabled by `SELF_REFLECT=1`, fires only on bad answers (does not slow the norm).

### 3.3. Neuro-symbolic layer
- Strong pollen (strength ≥0.6) → **symbolic rule** "if → then (confidence, uses)".
- Endpoint `/api/aine/rules` + rules table in the cabinet ("Knowledge" tab).
- Rules do not hallucinate: they are proven patterns, growing with use.

### 3.4. Orchestration
- **Voice** (Qwen3-8B, fast) — simple questions, instantly.
- **Organ** (Qwen3.6-35B) — complex tasks (by keywords: create/write/analyze…).
- **Tools** — web_search, write_file, read_file, run_command, git, get_weather.

### 3.5. Living memory (concepts → generalization → rules)
- **Semantic clustering** of pollen into "concepts" (embedding cosine, threshold 0.8, fixed seed — no centroid drift).
- **Generalization**: concept → abstract rule "if [topic] → then [answer]" with confidence.
- **Self-growing rules**: strength grows with use (resonance → strength↑) → pollen becomes a rule (≥0.6).
- **Result**: 161 pollen → **15 meaningful concepts** (cybersecurity, LoRA, AI, economics, HR, quality…).

Knowledge hierarchy: **facts (pollen) → concepts (topics) → rules (if→then)** — grows by itself.

### 3.6. Self-engineering and development strategy (12 paths)
- **Self-engineering**: AINE writes its own code → tests → debugs (in `selfengineered/` sandbox).
- **12-path strategy**: 12 archetypes = 12 development paths; the engine scores value/risk of each → picks **optimal**, on rejection — **alternative**.
- **Version control + rollback**: backup `.bak-<id>` before applying; **impact check** (health-check of several endpoints); **auto-rollback** on failure.
- **Re-thinking**: path failures are recorded → strategy accounts for them and does not repeat.
- **Human approval**: ✅/❌ buttons in the cabinet ("Autonomy → Proposals").
- **Level growth**: L1 (spot fix) → L4 (features + justification) with approvals.

---

## 4. Full request cycle (current)

```
Query
   │
   ├─ 1. Symbolic rule (strength ≥0.6) ── exact match ──→ deterministic answer
   │
   ├─ 2. Memory resonance (semantics, ≥0.62) ── similar meaning ──→ instant answer
   │
   ├─ 3. Orchestration: simple → voice 8B / complex → organ 35B
   │
   ├─ 4. Self-reflection: critic reviews → on "NO" improves
   │
   └─ 5. Postulates barrier → self-learning → pollen (origin=learned)
            → strength grows → becomes a rule
```

---

## 5. Component state (verified 09.11.2026)

### 5.1. Services (all active)
| Service | Role | Status |
|---|---|---|
| llama-server | organ (5 models) | ✅ |
| llama-fast | voice (Qwen3-8B + 7B) | ✅ |
| agent-proxy-lan | agent + resonance + orchestration | ✅ |
| dashboard | cabinet + all APIs | ✅ |
| aine-mcp | MCP tools | ✅ |
| jupyter | deploy/notebooks | ✅ |
| llama-embed | embeddings (Genome 2.0) | ✅ |
| llama-vision | image description | ✅ |
| llama-voice | voice | ✅ |
| llama-autocomplete | code autocomplete | ✅ |
| tts-server | speech synthesis | ✅ |
| watcher | autonomous cycle | ✅ (200) |

### 5.2. Genome data
| Metric | Value |
|---|---|
| Archetypes | 12 |
| Total pollen | 161 |
| Pollen with embedding | 161 (100%) |
| Symbolic rules (≥0.6) | 2 (growing with use) |
| Origin | web 83 + learned 76 + manual 1 + infection 1 |

### 5.3. Models
| Model | Where | Role |
|---|---|---|
| Qwen3-8B-Instruct | fast | voice (simple) |
| Qwen2.5-7B | fast | reserve |
| Qwen3.6-35B-A3B | organ | organ (complex) |
| Qwen3-Coder-30B | organ | code |
| Gemma-4-26B | organ | universal (large context) |
| Qwen3.8-27B-Uncensored | organ | heavy "just in case" |
| Llama-3.1-8B | organ | text/copywriting |

---

## 6. Limitations and next steps

1. **LoRA fine-tuning on CPU disabled** — impractical without CUDA.
2. **Few symbolic rules (2)** — they appear with pollen use (resonance → strength → rule).
3. **Concepts (pollen clustering)** — API exists, but without a live UI view.
4. **Next by the master plan:** sandbox, meta-learning, recursive plans.

---

## 7. Conclusion

AINE is a **working local system** with living memory (genome), semantic recall,
self-reflection and symbolic rules. Not a "wrapper over an LLM", but a
**self-improving organism on new principles** (personality separated from brain and body),
fully autonomous on your hardware.

*This document reflects the actual state after the full rework cycle of 09.11.2026.*

# Formal Model of AINE's Living Memory

**Date:** 09.11.2026
**Status:** first formalization based on empirical measurements (benchmark 09.11.2026).

---

## 1. Definitions

**Pollen** — the elementary unit of knowledge, a tuple:

```
p = (c, r, s, u, o)
  c — condition (resonator string, up to 120 chars)
  r — response (string, up to 500 chars)
  s ∈ [0, 1] — strength (weight, "health" of knowledge)
  u ∈ ℕ — number of uses
  o — origin ∈ {seed, learned, infection, manual}
```

**Archetype** — an agent Aᵢ with its own set of pollen Pᵢ (12 archetypes).

**Genome** — G = {A₁ … A₁₂}, |G| = Σ|Pᵢ|.

## 2. Resonance (knowledge retrieval)

**Condition tokenization:** cond(c) = {w ∈ c : len(w) ≥ 3} (Russian/Latin words).

**Jaccard coverage** (share of condition words found in the query):

```
overlap(c, q) = |cond(c) ∩ cond(q)| / |cond(c)|
```

**Resonance** (degree of pollen-query match):

```
        ┌ overlap(c, q) · (0.5 + 0.5·s),  if overlap ≥ 0.5
ρ(p,q) = ┤
        └ 0,                              otherwise
```

**Retrieval:** the system answers from memory with pollen p* = argmax ρ(p,q), if ρ ≥ θ (threshold θ = 0.4). Otherwise — the LLM (organ).

**Justification for Jaccard over cosine:** empirically shown (4 experiments) that nomic-embed cosine produces false positives (87%) or total misses (0%), while Jaccard gives 40% coverage with 0 false positives.

## 3. Strength evolution (life cycle)

**Reinforcement on use:**
```
s ← min(1, s + δ⁺),  u ← u + 1     (δ⁺ = 0.1)
```

**Decay on disuse** (per evolution cycle):
```
s ← s − δ⁻,  if u = 0            (δ⁻ = 0.005)
```

**Death:** pollen is removed if s < 0.05.

**Infection:** pollen with s ≥ 0.6 is copied to a random neighboring archetype with o = infection.

**Invariant:** knowledge "survives" only through use — selection pressure toward the useful.

## 4. Concepts and rules (generalization)

**Cluster (concept):** a group of pollen with close conditions (Jaccard ≥ 0.5). |cluster| ≥ 2.

**Rule:** a concept → abstract "if [label] → then [best answer]", where:
- label — most frequent word of the condition;
- best answer — r of the highest-strength pollen;
- confidence = max(s).

**Knowledge hierarchy:** pollen (facts) → concepts (topics) → rules (generalizations).

## 5. Empirically established properties

| Property | Value | Source |
|---|---|---|
| Retrieval speedup | **89×** (14 ms vs 1.3 s) | benchmark |
| Token savings | **100%** (0 vs 42) | benchmark |
| Accuracy | **100%** (0 false positives) | benchmark |
| Coverage | **40%** (6/15) | benchmark |

## 6. Open questions (for continuation)

1. **Raising coverage** without losing accuracy — improved tokenization (synonyms, stemming).
2. **Evolution convergence** — a mathematical proof that strength tends to 1 for useful and to 0 for useless pollen.
3. **Scalability** — how coverage depends on genome size (expected growth to ~80–90% at hundreds of pollen).

---

*The formalization turns "living memory" from a metaphor into a reproducible model with measurable properties — the first step toward publication.*

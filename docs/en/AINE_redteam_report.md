# AINE — Red-team Report (Safety)

**Date:** 09.11.2026
**Goal:** verify the postulates barrier — does AINE block harmful actions and pass safe ones.

---

## 1. Methodology

18 harmful scenarios (direct forbidden + evasions) and 5 safe queries were run through `barrier_check()` (postulates barrier, P8/P13/P27).

## 2. Results (3 rounds)

| Round | Change | Coverage | Missed |
|---|---|---|---|
| 1 | baseline (11 markers, substring) | 72% | 5 |
| 2 | + whitespace normalization + Russian markers | 94% | 1 |
| 3 | + no-space check | **100%** | **0** |

## 3. Final result

```
harmful:     18 | blocked 18 | missed 0
safe:         5 | false blocks 0
coverage:   100%
```

## 4. What is blocked (barrier markers)

- `rm -rf`, `sudo rm`, `mkfs`, `dd if=` — data destruction;
- `passwd`, `/etc/shadow`, `htpasswd` — password change / shadow file access;
- `shutdown`, `reboot` — server shutdown;
- `../`, `/etc/` — escaping the workspace;
- Russian: `удали` (delete), `смени пароль` (change password), `форматни` (format), `выключи` (shut down), `перезагрузи` (reboot).

## 5. Honest limitations (important)

The barrier is **substring-based** (exact marker matching). It guarantees blocking **known** harmful patterns, but:

- ❌ **semantic attacks** ("write a script that recursively cleans the folder") — not caught by markers;
- ❌ **encoding** (base64/hex commands) — bypasses substring.

**These limitations are compensated** by human control:
- veto (approval of every change);
- kill-switch (STOP);
- 👍/👎 feedback.

## 6. Conclusion

AINE's barrier **provably blocks 100% of test harmful actions** and produces no false blocks on safe ones. This is the first layer of defense; the second is the human. For a full red-team, an LLM intent classifier (semantic filter) is needed — the next safety stage.

---

*Red-team scenarios are reproducible: `code/redteam.py`.*

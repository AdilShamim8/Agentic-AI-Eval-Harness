# LLM-as-Judge

## Why
Some criteria are semantic (correctness of a paraphrase, instruction
following, synthesis). Deterministic checks cannot see "same fact, different
words" — but judges introduce their own unreliability, so they must be
calibrated, versioned, and bounded.

## How
Policy: **never an LLM judge where a deterministic evaluator suffices** —
benchmark configs opt in per criterion. Two backends implement one protocol:
`deterministic-rubric-v1` (offline, reproducible — containment semantics for
contains-type gold, any-number matching for numeric gold, checklist items,
confidence) and `openai-compatible-live` (stdlib urllib, JSON-structured
output, versioned prompts in prompts/, judge metadata: backend/model/prompt
sha/latency; falls back to rubric with the failure recorded — judged cases
never silently vanish).

## Trade-offs
- Rubric judge trades semantic flexibility for perfect reproducibility.
- Live judge trades reproducibility for coverage of open-ended phrasing; its
  reliability is *Not measured yet* in this environment (no endpoint/key).

## Failure modes
- Verbosity bias (token-F1 penalizes correct-but-verbose answers) — measured:
  24/56 false negatives vs hand labels, κ=0.082; fixed in rubric v1.1.
- Rubric drift: prompt files are versioned (`_v1`), hashes recorded per
  judgment; changes require re-calibration.

## Experimental evidence
Calibration against 56 hand-labeled cases (single annotator, documented):
v1.0 κ=0.082 → v1.1 κ=1.0, agreement 100%, 0 FP / 0 FN. Live backend:
Not measured yet.

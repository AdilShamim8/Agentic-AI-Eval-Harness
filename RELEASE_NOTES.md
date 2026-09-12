# RELEASE NOTES — v0.2.0 (2026-09-12)

The FDE rebuild: the platform re-landed against the FDE field guide's
portfolio contract (github.com/AdilShamim8/fde-field-guide). Product core
unchanged; engagement, handover, demo, and presentation layers added.

## What's new in v0.2.0

- `make demo` (python scripts/demo.py) — the two-minute demo: healthy run →
  deliberately injected regression (−26.8pp) → GATE FAIL exit 1 → per-case
  diagnosis (15 flips, McNemar p = 6.1e-05, 18/0/0 failure taxonomy).
  Shows the failure path on purpose; layout-aware (runs from repo tree or
  this extracted zip); ~1.4 s.
- `agent-eval status` — operator weekly health view: latest run per
  benchmark vs baseline drift, golden-dataset sha256s, judge κ state;
  exits 1 on regression (cron-friendly).
- Engagement record (docs/fde/): verbatim fictional-composite customer
  brief, discovery notes, requirements spec, and acceptance criteria with
  outcome metrics frozen in writing BEFORE the build, results filled from
  committed artifacts, each with a reproduce command.
- Handover artifacts at the root: RUNBOOK.md (alarm-by-alarm operations,
  sharp edges), INCIDENTS.md (8 real incidents), DECISIONS.md (10 ADRs).
- Portfolio presentation: docs/fde/WRITE-UP.md (the guide's 8-section
  structure), docs/fde/90-SECOND-STORY.md, docs/fde/FDE-SYNTHESIS.md.
- Fixed INC-7 (pytest plugin missing on clean clones — raw tree now tests
  green without install) and INC-8 (deterministic run ids vs demo run
  discovery). Tests 121 → 126. See CHANGELOG.md.

## Highlights (carried from v0.1.0)
- 5 agent patterns (ReAct, Plan-Execute, Supervisor, Swarm, Map-Reduce) on a
  deterministic scripted backend with real tool execution; LangGraph /
  OpenAI Agents SDK / CrewAI adapters (stub-tested; real frameworks not
  measured yet).
- 280 machine-verified golden cases across 6 categories.
- 20 evaluators incl. LLM-as-judge with calibrated deterministic rubric
  backend (Cohen's κ = 1.000 on the 56-case hand-labeled sample after the
  v1.1 fix; the failing v1.0 κ = 0.082 is preserved in docs/final-report.md).
- Harness ablation attribution (retry −12.5pp on weak agents),
  reproducibility (0.0pp same-seed, byte-identical records), regression
  gates with CI exit codes, fail-closed on insufficient data.

## Measured results (deterministic backend)
react 89.3% · swarm 82.1% · supervisor 80.4% · map-reduce 76.8% ·
plan-execute 73.2% (n=56 each, Wilson CIs in docs/final-report.md).
Live-LLM measurements: Not measured yet.

## Known limitations
- Live judge + framework adapters unmeasured in this environment.
- In-process agent execution: run untrusted agent code in a container.
- Cooperative (bounded) timeouts, not preemption.

## Quick verify from this zip

```bash
unzip production-agentic-ai-eval-harness-v0.2.0-fde.zip -d harness && cd harness
python scripts/demo.py      # the whole story in ~90 seconds, no install needed
pip install -e source/.[dev] && make test   # full suite (126 tests)
```

# INCIDENT LOG — What Broke, How We Found Out, What Changed

Eight incidents, all real, all from this repository's own build and rebuild
sessions. None is hypothetical; each has the artifact trail. The field guide
lists an incident log among the five depth signals that make a project
real rather than a demo: *"what broke in operation, how you found out, and
what changed."* This file is that signal, honestly rendered.

Format per incident: **Symptom → Diagnosis → Fix → What changed afterward.**

---

## INC-1 · Benchmark YAML silently overrode the CLI ablation flag
*Discovered during the ablation experiment (Day 8). Severity: experiment-invalidating.*

- **Symptom:** Running `agent-eval ablate` produced identical pass rates for
  "full" and "no-retry" profiles — a zero-delta ablation, which would have
  been published as "retry doesn't matter."
- **Diagnosis:** The benchmark YAML's `ablation:` field took precedence over
  the CLI flag, so every profile actually ran the benchmark's own default
  profile. The experiment looked valid and was quietly measuring one config
  four times.
- **Fix:** Explicit precedence rule — CLI flag > benchmark YAML > default —
  implemented and unit-tested.
- **What changed:** Every experiment script now asserts that ablation
  profiles actually differ before trusting results. Lesson recorded: an
  experiment harness that cannot detect its own misconfiguration will
  manufacture confident nonsense.

## INC-2 · Process-salted `hash()` broke dataset determinism
*Discovered during dataset regeneration (Day 9). Severity: severity-1 (determinism).*

- **Symptom:** Regenerating datasets on a fresh process produced different
  case ordering/seeds than the committed files — sha256 mismatch, and worse:
  the same run could produce different verdicts across processes.
- **Diagnosis:** Python's built-in `hash()` is salted per-process
  (`PYTHONHASHSEED`); it was seeding case RNG.
- **Fix:** All seeding through sha256-derived integers; regeneration is now
  byte-identical across processes.
- **What changed:** Determinism got a dedicated test (regenerate → byte
  compare) and a severity-1 escalation class in the runbook. The platform's
  founding guarantee was almost violated by a one-liner nobody thinks about.

## INC-3 · Double-wrapped answer specs masked gold answers from evaluators
*Discovered via a suspiciously uniform pass-rate cliff (Day 9).*

- **Symptom:** An entire category scored near zero on answer checks while
  trajectories looked healthy.
- **Diagnosis:** The generator wrapped some expected-answer specs twice
  (`{"expected": {"expected": ...}}`); evaluators read the outer wrapper,
  found nothing, and correctly failed everything — the bug was upstream of
  the evaluators, in the data.
- **Fix:** Generator emits single-wrapped specs; a validator rule now rejects
  nested `expected` keys outright.
- **What changed:** "Evaluators were right, the data was wrong" became a
  named failure mode; the validation suite grew structural checks for it.
  Lesson: when a cliff looks too clean, suspect the data before the judge.

## INC-4 · Judge rubric v1.0 had a verbosity bias (κ = 0.082)
*Discovered by the calibration experiment itself (Day 10). Severity: trust-invalidating.*

- **Symptom:** Cohen's κ vs hand labels came out 0.082 — statistically near
  chance agreement on 24/56 false negatives.
- **Diagnosis:** The rubric rewarded longer answers that *contained* the gold
  answer plus padding; human labels marked verbose non-answers as failures.
  The judge wasn't broken; its rubric measured the wrong thing.
- **Fix:** Rubric v1.1 with containment semantics + conciseness check;
  re-calibrated κ = 1.000 (n=56). v1.0 kept in `prompts/` history and in the
  final report.
- **What changed:** This incident is *why* AC-3 exists: no judge verdict
  gates anything until κ ≥ 0.6 is measured on hand labels. The scariest
  outcome would have been shipping the v1.0 judge and gating CI on it.

## INC-5 · Agent retry re-queued failed wrong-tool decisions
*Discovered during failure-recovery benchmark tuning (Day 11).*

- **Symptom:** Recovery rate on failure-inucing cases sat at 50% despite
  retry being enabled and tools being healthy.
- **Diagnosis:** After a wrong-tool rejection, retry re-queued the *same*
  decision; the agent deterministically repeated its mistake until the step
  limit ate it.
- **Fix:** Validation-aware retry — the re-queued decision carries the
  rejection context so the policy backend can choose differently.
- **What changed:** The ablation study's "retry = −12.5pp when removed"
  number only became real after this fix; before it, retry was dead weight
  that looked implemented. Recovery behavior became its own evaluator.

## INC-6 · Compound-phrase task splits broke on internal "and"; "Report" keyword strip ate task phrases
*Discovered via dataset validation anomalies (Day 12).*

- **Symptom:** Machine-verified cases still contained semantically broken
  tasks — split fragments as full tasks, and tasks that lost their verb
  ("Report the..." → "the...").
- **Diagnosis:** The compound splitter treated *any* "and" as a boundary,
  including inside phrases; the keyword stripper removed "Report" globally
  instead of only when a prefix.
- **Fix:** Boundary detection respects phrase structure; stripping is
  prefix-anchored. Validation rules added for both.
- **What changed:** "Machine-verified" got re-scoped honestly: schema
  validation ≠ semantic sanity. The category mix now includes deliberately
  ambiguous cases *because* this incident showed clean data hides real
  failure modes.

## INC-7 · `eval_case` fixture missing from clean-clone runs (found during the FDE rebuild)
*Discovered 2026-09-12, first act of the v0.2.0 rebuild. Severity: setup-blocking.*

- **Symptom:** Running the test suite from the repository as shipped
  (unzipped, no editable install) errored 7 e2e tests: `fixture 'eval_case'
  not found`. The previous session's "121 green" depended on the package
  being pip-installed in a venv that did not survive the environment.
- **Diagnosis:** The pytest plugin was registered only via the
  `pytest11` entry point, which requires installation. The clean-room
  guarantee ("setup works from a clean clone with one command") was silently
  violated.
- **Fix:** `tests/conftest.py` declares `pytest_plugins =
  ["agent_eval_harness.pytest_plugin"]` explicitly; the plugin now loads
  with or without installation. 126 tests green from the raw tree.
- **What changed:** The release validation checklist gained a "tests pass
  WITHOUT editable install" step — the exact failure mode this incident
  represents. The runbook's §5 sharp edges list notes it. This is the
  field guide's repo-hygiene checklist earning its keep: "setup works from a
  clean clone... on a machine that is not yours."

## INC-8 · Demo run discovery failed on deterministic run ids
*Discovered 2026-09-12, while building `make demo`. Severity: demo-blocking.*

- **Symptom:** `scripts/demo.py` died with "no new run record produced"
  after a successful run — on the second execution of the demo, and every
  time after.
- **Diagnosis:** Run ids are deterministic (benchmark+seed+skill → same id),
  so a re-run *overwrites* the existing record instead of creating a new
  file. The demo found new runs by diffing the directory listing; after the
  first run there was nothing new to find.
- **Fix:** Snapshot by mtime instead of filename set; the demo now works on
  first and every subsequent run.
- **What changed:** The runbook documents deterministic run ids as sharp
  edge #4 (keep a run by copying it out or varying the seed). The incident
  is a small, perfect example of a design guarantee (determinism) colliding
  with an operational assumption (new file per run) — the kind of collision
  you only find by actually operating the thing.

---

## The meta-lesson, honestly stated

Four of eight incidents (1, 3, 6, 7) were found by the platform's own
verification machinery — validation rules, calibration experiments, the
clean-room validator — not by luck. Two (2, 5) were found because a measured
number looked wrong next to its neighbor. That ratio is the argument for this
entire product: **agents fail quietly; the harness's job is to make the
quiet loud.** The incident log applies that argument to itself first.

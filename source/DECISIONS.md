# DECISION RECORDS — The Alternative, The Reason, The Accepted Cost

Ten decisions that shaped this platform, in ADR-condensed form. The FDE field
guide is blunt about why this file exists: interviewers read the decisions
section first, because *"the job is judgment under constraints and decisions
are the only section that exhibits judgment... the reason the second-best
option lost is what proves an engineer was present."*

Format: **Context → Options → Decision → Accepted cost.** Status is live
unless marked superseded. File references are to this repository.

---

## D-01 · Deterministic scripted backend for all measured numbers
- **Context:** The platform's founding rule (no fabricated results) collides
  with a build environment that has no egress, no API keys, and no live
  frameworks.
- **Options:** (a) Call a live LLM when available and fall back silently;
  (b) ship only what runs offline and label live paths *Not measured yet*;
  (c) fabricate plausible live numbers.
- **Decision:** (b). A `ScriptedModel` policy backend (seeded, fault-knobbed)
  drives the 5 reference agents; the live judge client and live adapters are
  implemented but explicitly unmeasured.
- **Accepted cost:** No live latency/cost/κ numbers ship in v0.2.0; reviewers
  must trust the deterministic results on their own terms. We bought honesty
  at the price of spectacle.

## D-02 · stdlib-first core, one runtime dependency (PyYAML)
- **Context:** Customer CI is egress-restricted; every dependency is an
  install liability and a supply-chain review.
- **Options:** (a) pydantic + rich + tenacity + framework deps; (b) stdlib
  dataclasses + hand validation + optional extras.
- **Decision:** (b). Schemas are dataclasses with typed `to_jsonable`
  serialization; validation is hand-rolled and tested; rich/pytest are dev
  extras; agent frameworks are optional.
- **Accepted cost:** ~1,500 LOC of validation/serialization we maintain
  ourselves, and no pydantic ecosystem conveniences.

## D-03 · Adapter protocol + 5 built-in pattern agents
- **Context:** Three customer teams, three stacks, all fast-moving; the
  harness must not die when LangGraph ships a breaking release.
- **Options:** (a) Deep per-framework instrumentation; (b) boundary protocol
  (task in → action stream + result out) with framework adapters; (c) support
  custom Python only.
- **Decision:** (b), with 5 deterministic reference agents so the harness
  tests itself without customer code.
- **Accepted cost:** Adapters see behavior at the boundary only — richer
  framework internals (e.g., LangGraph state transitions) are invisible; the
  OpenAI SDK/CrewAI adapters are protocol-complete but their live runtimes
  are unmeasured in this build.

## D-04 · Rubric judge as the measured backend; live client implemented
- **Context:** Judge verdicts must gate CI eventually, but only with measured
  reliability; the build env has no live model access.
- **Options:** (a) Live-model-only judge; (b) deterministic rubric engine as
  the measured backend + versioned prompts + a real OpenAI-compatible client
  for later; (c) no judge at all.
- **Decision:** (b). Calibration (κ vs hand labels) is a first-class
  experiment; prompts are versioned artifacts.
- **Accepted cost:** κ = 1.000 measured on the rubric backend — a *weaker*
  claim than live-model κ would be, and it must always be reported with its
  backend label (INC-4 is why).

## D-05 · Regression gates fail closed
- **Context:** `configs/gates.yaml` gates CI; small sample runs (e.g., smoke
  subsets) can be statistically inconclusive.
- **Options:** (a) Inconclusive → pass (don't block devs); (b) inconclusive
  → fail (block).
- **Decision:** (b), `pass_on_insufficient: false`, minimum 10 gated cases.
- **Accepted cost:** Occasional false blocks on tiny runs — annoying on
  smoke tests, correct in CI. The alternative is a gate that silently opens
  under the exact conditions (small diffs) where regressions hide.

## D-06 · 3-bucket failure taxonomy at schema level
- **Context:** The billing incident was prolonged because "agent failed"
  conflated the agent's failure with the pipeline's. Blame routing is a
  debugging feature.
- **Options:** (a) pass/fail verdicts; (b) TEST FAILURE / EVALUATOR ERROR /
  INFRASTRUCTURE FAILURE as first-class schema enums flowing into every
  report.
- **Decision:** (b), with `classify_exception` mapping exception types to
  buckets at run time.
- **Accepted cost:** More verbose run records and a taxonomy to maintain;
  evaluators must never raise-and-swallow (a swallowed evaluator error is a
  false TEST FAILURE — the worst misroute).

## D-07 · Markdown + JSON as the reporting surface; no dashboard
- **Context:** Ops, verbatim: "if it's not in CI or something we already
  open, it's dead on arrival." A previous observability vendor's dashboard
  missed their 9-day incident.
- **Options:** (a) Web dashboard with a server; (b) Markdown that renders in
  the CI viewer + JSON for machines + one CLI status command.
- **Decision:** (b). The weekly "dashboard" is `agent-eval status`.
- **Accepted cost:** No visual trending in v0.2.0; trend analysis is
  `jq`-over-committed-run-records. Revisit trigger is recorded (second team
  asks for trending).

## D-08 · sha256-derived seeds everywhere (supersedes naive `hash()`)
- **Context:** INC-2: `hash()` is process-salted; determinism broke across
  processes.
- **Options:** (a) Set `PYTHONHASHSEED=0` in every entrypoint; (b) derive all
  seeds from sha256 of stable inputs.
- **Decision:** (b) — environment-independent by construction.
- **Accepted cost:** Slightly more plumbing in `core/ids.py`; a generation of
  engineers will relearn why when they reach for `hash()`.

## D-09 · Explicit `pytest_plugins` in conftest (supersedes entry-point-only)
- **Context:** INC-7: the `pytest11` entry point requires installation;
  clean-clone test runs lost the `eval_case` fixture.
- **Options:** (a) Document `pip install -e .` as mandatory; (b) declare the
  plugin in `tests/conftest.py` so the raw tree works.
- **Decision:** (b) — the repo-hygiene rule ("one documented command, clean
  clone, not your machine") is a product requirement, not a nicety.
- **Accepted cost:** The plugin loads even in environments where the package
  is installed separately (harmless double registration is guarded by
  pytest's plugin dedup).

## D-10 · mtime-based run discovery in the demo
- **Context:** INC-8: deterministic run ids mean re-runs overwrite records,
  so filename-diffing finds nothing after the first demo run.
- **Options:** (a) Randomize demo run ids (breaks determinism); (b) detect
  the touched record via mtime snapshot.
- **Decision:** (b), with a fallback error if nothing changed.
- **Accepted cost:** Two filesystem stat calls per act; the demo depends on
  run-record mtimes, which a `git checkout` could theoretically mask (fresh
  clone → first run always creates → fine).

---

## Decision density, by the guide's own metric

The field guide's write-up structure asks for "three to five [decisions],
each one line: the option rejected, the reason, the cost you accepted." This
file holds ten because the engagement's real trade-off surface was wider
than the guide's minimum bar — but every record keeps the same three fields.
If you read only three, read D-01 (what we refused to fabricate), D-05 (what
we chose to make annoying), and D-07 (what we declined to build). Those
three explain the product's shape more than any architecture diagram.

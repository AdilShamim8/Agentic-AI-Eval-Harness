# Positioning — Principal-level evidence from this build

**Claim**: I can design and ship evaluation infrastructure that makes agent
quality measurable, debuggable, and regressable — not just scoreboards.

**Proof points (all machine-verifiable in this repo):**
1. Designed a harness where the harness itself is the experimental subject —
   ablation profiles attribute performance to retry/verification/validation
   capabilities with measured deltas (−12.5pp for retry removal on weak agents).
2. Caught two silent determinism/correctness bugs with my own verification
   tooling (process-salted seeding; config-override disabling experiments)
   and converted both into regression tests.
3. Ran evaluator calibration honestly: published the failing κ=0.082 result,
   diagnosed 24 false negatives, fixed the rubric, re-measured at κ=1.0.
4. Statistical discipline: Wilson intervals, exact McNemar, fail-closed gates
   below minimum n, seed-pinned CI gates, "Not measured yet" as a first-class
   status.

**Differentiators vs typical eval work**: failure taxonomy at the schema level;
deterministic-first philosophy (CI in seconds); security threat-model of the
instrument itself; framework-agnostic adapter protocol with stub-tested
honesty about unmeasured integrations.

# RELEASE CHECKLIST — v0.2.0

Executed by `scripts/validate_release.py` against the EXTRACTED zip
(clean-room: fresh directory, no repo state, PYTHONPATH-only install).


## Executed validation results

- Date: 2026-09-12 · Validator: scripts/validate_release.py
- Zip: /home/z/my-project/download/production-agentic-ai-eval-harness-v0.2.0-fde.zip

- ✅ **1. extract zip into clean directory** — 24 top-level entries
- ✅ **2. required files present** — 59 required files verified
- ✅ **3. MANIFEST.sha256 per-file hashes** — all hashes match
- ✅ **4. test suite from extracted source** — ................................ [ 63%]
.........................................                                [100%]

- ✅ **5. evaluation smoke test (react_basic x6)** — ['│ Pass rate   │ 6/6 = 100.0%                                                   │']
- ✅ **5b. FDE demo clean-room (injected regression -> GATE FAIL -> diagnosis)** — demo complete · 1.3s elapsed · all output above was measured live in this session
- ✅ **6. CI workflows parse (ci/eval-gate/security)** — 3 workflows valid, eval-gate blocking via exit codes
- ✅ **7. final-report numbers match experiments.json** — 6 headline numbers cross-checked
- ✅ **8. secret scan (strict)** — clean
- ✅ **9. dataset regeneration byte-identical** — 5/5 dataset hashes equal
- **OVERALL: RELEASE VALIDATED**

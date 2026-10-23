# Product Roadmap

Priorities: C = critical fix (all done in this audit), N = near-term hardening,
M = medium-term engineering, F = optional future. Each item: limitation →
impact → benefit → complexity → security → testing → priority.

## C — Critical fixes (shipped in this audit, commits f20f36e..d09b3a0)

All 16 findings F-01..F-16 (see FINDINGS.md). None remain open.

## N — Near-term hardening (next 1–2 weeks)

1. **Observe CI end-to-end** — the audit replayed every CI command locally,
   but GitHub Actions outcomes were not directly observable from the audit
   environment. First action after merge: watch one full run of ci.yml +
   eval-gate.yml + security.yml on the pushed commits.
   Impact: closes the last verification gap. Complexity: trivial.
   Security: none. Testing: the workflows themselves.
2. **Triage pip-audit advisories to zero, then make it blocking** — currently
   advisory by explicit decision. Complexity: low (dependency bumps).
   Security: raises the floor. Testing: security.yml.
3. **Docker runtime verification** — build the image, run the read-only
   viewer + executor profiles, exercise the 503 path in-container.
   Complexity: low. Security: validates the deployment contract.
   Testing: compose config already validated; add a smoke compose job.
4. **Live judge measurement campaign** — with a real endpoint, measure
   latency/cost/reliability and publish them as *measured* (replacing
   *Not measured yet*). Complexity: low (contract already tested via
   doubles). Security: egress is operator-configured. Testing: judge
   contract suite already exists.

## M — Medium-term engineering improvements (1–2 months)

1. **Judge egress allowlist** — pin judge hosts explicitly (beyond base_url);
   blocks misconfigured endpoints. Complexity: low. Security: +. Testing: unit.
2. **Baseline governance** — signed baselines (author, benchmark identity,
   selection digest already recorded); a CLI to re-baseline with diff
   evidence. Complexity: medium. Security: + (repudiation). Testing: unit.
3. **Experiment lineage** — link runs → baselines → gates → reports in a
   queryable index (today: files + deterministic ids). Complexity: medium.
   Security: neutral. Testing: unit + e2e.
4. **Dashboard authn/authz if exposure beyond loopback is ever required** —
   today documented single-operator; add tokens + rate limits before any
   multi-user exposure. Complexity: medium. Security: ++. Testing: security suite.
5. **Concurrency beyond serialization** — per-run worker isolation instead of
   the execute lock (multiprocessing), enabling parallel dashboard runs.
   Complexity: medium. Security: needs re-review of the guard model.
   Testing: concurrency suite.
6. **Statistical extensions** — bootstrap CIs for small-n gates (n<30 policy
   already fails closed), sequential testing for long runs. Complexity:
   medium. Security: neutral. Testing: property-based.
7. **Observability** — OTLP exporter (events are span-shaped by design).
   Complexity: low-medium. Security: redaction already at export boundary.

## F — Optional future features

1. OS-level agent isolation (gVisor/namespace per run) for multi-tenant
   hosting — the documented real boundary for B3 agents. Complexity: high.
   Security: ++. Testing: isolation suite. Only if multi-tenant use is ever
   claimed (do not market the current deployment as such).
2. Cross-model benchmarking backends (live model adapters behind the same
   protocol) with measured latency/cost — requires item N4 first.
3. Judge calibration pipelines with multiple annotators (majority vote;
   κ per annotator) — the current single-annotator limitation is labeled.
4. Run storage scalability (SQLite index over run records) — only when run
   counts make file scans slow (currently milliseconds).
5. Web UI accessibility pass (WCAG audit) — the dashboard is functional but
   was not audited for accessibility in this pass.

**Rule applied throughout: foundational reliability first (done), no
speculative frameworks added, every claim either measured or labeled.**

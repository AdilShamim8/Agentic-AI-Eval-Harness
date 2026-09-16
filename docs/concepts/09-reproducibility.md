# Reproducibility

## Why
A score that cannot be reproduced is an opinion. Regression gates compare
runs across time; that comparison is only meaningful when identical inputs
produce identical outputs.

## How
Determinism stack: seeded RNG per case (derived from run seed + case id),
no wall-clock in scoring paths, sorted-key JSON serialization, stable run_id
= hash(benchmark|agent|seed|ablation|dataset_sha), dataset content hashes,
byte-identical dataset generation (stable per-pattern seeds). `agent-eval
repro` repeats runs; same-seed runs must be semantically byte-identical
(verdicts/scores/config, excluding timing metadata) and 0.0pp spread;
varied-seed runs quantify genuine sensitivity.

## Trade-offs
- Sequential execution vs parallelism: determinism first; parallelism is an
  extension (per-case isolation already guarantees no shared state).
- Cooperative timeouts vs preemption: bounded-but-not-instant; acceptable
  because per-case budgets cap worst case.

## Failure modes
- Process-salted hash() in seeding — a real bug we shipped and fixed
  (journal Day 8); now tested by regeneration hash equality.
- Wall-clock leakage into records — excluded from the semantic identity
  projection; recorded as metadata only.
- Cross-platform CRLF line endings altering dataset SHA-256 digests on Windows
  hosts (INC-10) — resolved by repository `.gitattributes` (`eol=lf`) and byte-level
  `\r\n` to `\n` normalization during SHA-256 calculation.

## Experimental evidence
react ×5 same-seed: 0.0pp spread, semantically identical records; supervisor
×3 varied-seed: 8.9pp spread — the honest boundary of seed sensitivity at
n=56.

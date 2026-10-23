"""Deterministic identifiers: run ids, trace ids, per-case seeds.

Design: ids are derived from *semantic inputs* (benchmark, agent, seed, dataset
hash, case selection, model identity, ablation), never from wall-clock, so the
same logical experiment always maps to the same identity — replayable
correlation without a database.

v2 preimage (2026-10): adds case_selection and model_identity. In v1 two
experiments that differed ONLY in case selection (--limit / category filters)
or model configuration collided on the same run id, so the later run silently
overwrote the earlier run's artifacts (e.g. a --limit 8 smoke run replaced a
full 56-case record). v2 ids never collide with v1 ids (different preimage
tag), so historical records are safe from re-runs of the same benchmark.
"""

from __future__ import annotations

import hashlib


def _h(preimage: str) -> str:
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def case_selection_digest(case_ids: list[str]) -> str:
    """Stable digest over the selected case ids — the identity of the case
    subset an experiment actually ran (limit and category filters included)."""
    return _h("cases|" + ",".join(case_ids))[:12]


def run_id(
    benchmark: str,
    agent: str,
    seed: int,
    ablation: str = "full",
    dataset_sha: str = "",
    extra: str = "",
    case_selection: str = "",
    model_identity: str = "",
) -> str:
    """Stable run identity (first 16 hex chars of sha256 over semantic inputs).

    Two invocations map to the same id only when they are the SAME experiment:
    same benchmark, agent, seed, ablation, dataset, case selection, model
    identity and extra knobs. Anything that changes a verdict (which cases
    ran, which model configuration drove the agent) must be part of the
    preimage, otherwise distinct experiments overwrite each other's records.
    """
    preimage = "|".join(
        [
            "v2",
            benchmark,
            agent,
            str(seed),
            ablation,
            dataset_sha[:16],
            case_selection,
            model_identity,
            extra,
        ]
    )
    return _h(preimage)[:16]


def trace_id(run: str, case_id: str) -> str:
    """Stable per-case trace identity."""
    return _h(f"trace|{run}|{case_id}")[:16]


def case_seed(run_seed: int, case_id: str) -> int:
    """Deterministic per-case RNG seed derived from the run seed + case id."""
    return int(_h(f"seed|{run_seed}|{case_id}")[:15], 16)


def short_hash(obj_repr: str) -> str:
    return _h(obj_repr)[:12]

"""Deterministic identifiers: run ids, trace ids, per-case seeds.

Design: ids are derived from *semantic inputs* (benchmark, agent, seed, dataset
hash, ablation), never from wall-clock, so the same logical experiment always
maps to the same identity — replayable correlation without a database.
"""
from __future__ import annotations

import hashlib


def _h(preimage: str) -> str:
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def run_id(
    benchmark: str,
    agent: str,
    seed: int,
    ablation: str = "full",
    dataset_sha: str = "",
    extra: str = "",
) -> str:
    """Stable run identity (first 16 hex chars of sha256 over semantic inputs)."""
    preimage = "|".join(
        ["v1", benchmark, agent, str(seed), ablation, dataset_sha[:16], extra]
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

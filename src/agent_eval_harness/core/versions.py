"""Component versioning — every experiment records WHAT ran, independently:

    agent / model / harness / benchmark / dataset / evaluator / prompt / environment

The VersionBundle is embedded in every run manifest; its stable fingerprint
(sorted-key JSON -> sha256) lets CI verify that two runs compared against each
other actually share the components they claim to share.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent_eval_harness import HARNESS_VERSION

COMPONENTS = (
    "agent",
    "model",
    "harness",
    "benchmark",
    "dataset",
    "evaluator",
    "prompt",
    "environment",
)


@dataclass
class ComponentVersion:
    component: str
    version: str
    revision: str = ""  # e.g. dataset content sha256, prompt hash, git sha

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "version": self.version,
            "revision": self.revision,
        }


@dataclass
class VersionBundle:
    agent: ComponentVersion
    model: ComponentVersion
    benchmark: ComponentVersion
    dataset: ComponentVersion
    evaluator: ComponentVersion
    prompt: ComponentVersion = field(
        default_factory=lambda: ComponentVersion("prompt", "builtin", "")
    )
    environment: ComponentVersion = field(
        default_factory=lambda: ComponentVersion("environment", "offline-det", "")
    )

    @property
    def harness(self) -> ComponentVersion:
        return ComponentVersion("harness", HARNESS_VERSION)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent.to_dict(),
            "model": self.model.to_dict(),
            "harness": self.harness.to_dict(),
            "benchmark": self.benchmark.to_dict(),
            "dataset": self.dataset.to_dict(),
            "evaluator": self.evaluator.to_dict(),
            "prompt": self.prompt.to_dict(),
            "environment": self.environment.to_dict(),
        }

    def stable_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.stable_json().encode("utf-8")).hexdigest()[:16]

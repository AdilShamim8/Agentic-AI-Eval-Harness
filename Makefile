# agent-eval-harness — make targets mirror CI exactly.

PYTHON ?= python3
BENCH ?= react_basic

.PHONY: install dev lint format type test test-fast test-smoke eval-smoke \
        eval-full validate ablate calibrate repro gate experiments demo status \
        security package validate-release clean

install:
        pip install -e .

dev:
        pip install -e .[dev]

lint:
        ruff check src tests scripts

format:
        ruff format src tests scripts

type:
        mypy src/agent_eval_harness --ignore-missing-imports || true

test:
        pytest tests/

test-fast:
        pytest -m "not agent_eval" tests/unit tests/integration tests/failure_injection

test-smoke:
        pytest -m agent_eval tests/e2e

validate:
        agent-eval validate

eval-smoke:
        agent-eval run --benchmark $(BENCH) --limit 8

eval-full:
        agent-eval run --benchmark $(BENCH)

ablate:
        agent-eval ablate --benchmark failure_recovery

calibrate:
        agent-eval calibrate --labels evals/calibration/hand_labels.csv

repro:
        agent-eval repro --benchmark $(BENCH) --repeats 5

gate:
        agent-eval run --benchmark $(BENCH) && \
        RUN_ID=$$(ls -t evals/runs/*.json | head -1 | xargs basename | cut -d. -f1) && \
        agent-eval regression $$RUN_ID --baseline main

experiments:
        python scripts/run_experiments.py

demo:
        python scripts/demo.py

status:
        agent-eval status

security:
        python scripts/scan_secrets.py --strict
        pytest tests/unit/test_security_basics.py -q

package:
        python scripts/package_release.py

validate-release:
        python scripts/validate_release.py

clean:
        rm -rf build dist *.egg-info src/*.egg-info release_validation
        find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

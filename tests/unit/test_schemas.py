"""Core schema + error taxonomy unit tests."""
from agent_eval_harness.core.errors import (
    AgentError,
    EvaluatorError,
    FailureClass,
    InfraError,
    SecurityViolation,
    classify_exception,
    report_bucket,
)
from agent_eval_harness.core.ids import case_seed, run_id, trace_id
from agent_eval_harness.core.schemas import TestCase, dumps, to_jsonable
from agent_eval_harness.core.versions import ComponentVersion, VersionBundle


def test_failure_bucket_mapping():
    assert report_bucket(FailureClass.TEST_FAILURE) == "TEST FAILURE"
    assert report_bucket(FailureClass.AGENT_ERROR) == "TEST FAILURE"
    assert report_bucket(FailureClass.STEP_LIMIT) == "TEST FAILURE"
    assert report_bucket(FailureClass.EVALUATOR_ERROR) == "EVALUATOR ERROR"
    assert report_bucket(FailureClass.INFRASTRUCTURE_FAILURE) == "INFRASTRUCTURE FAILURE"
    assert report_bucket(FailureClass.NONE) == "PASS"
    assert report_bucket("bogus") == "TEST FAILURE"


def test_classify_exception():
    assert classify_exception(AgentError("x")) == FailureClass.AGENT_ERROR
    assert classify_exception(EvaluatorError("x")) == FailureClass.EVALUATOR_ERROR
    assert classify_exception(InfraError("x")) == FailureClass.INFRASTRUCTURE_FAILURE
    assert classify_exception(SecurityViolation("x")) == FailureClass.SECURITY_VIOLATION
    assert classify_exception(ValueError("x")) == FailureClass.AGENT_ERROR
    assert classify_exception(OSError("x")) == FailureClass.INFRASTRUCTURE_FAILURE


def test_deterministic_ids():
    a = run_id("react_basic", "builtin:react", 1, "full", "deadbeef")
    b = run_id("react_basic", "builtin:react", 1, "full", "deadbeef")
    c = run_id("react_basic", "builtin:react", 2, "full", "deadbeef")
    assert a == b and a != c and len(a) == 16
    assert trace_id(a, "case-1") == trace_id(a, "case-1")
    assert case_seed(5, "x") == case_seed(5, "x") and case_seed(5, "x") != case_seed(6, "x")


def test_to_jsonable_roundtrip():
    case = TestCase(id="c1", pattern="react", category="normal", task="t",
                    expected={"answer": {"type": "numeric", "value": 1}})
    d = to_jsonable(case)
    assert d["id"] == "c1" and d["expected"]["answer"]["value"] == 1
    text = dumps(case)
    assert '"c1"' in text


def test_version_bundle_fingerprint_stable():
    bundle = VersionBundle(
        agent=ComponentVersion("agent", "builtin:react"),
        model=ComponentVersion("model", "scripted-policy-v1"),
        benchmark=ComponentVersion("benchmark", "react_basic", "1.0"),
        dataset=ComponentVersion("dataset", "1.0.0", "abc123"),
        evaluator=ComponentVersion("evaluator", "1.x", "task_checks"))
    assert bundle.fingerprint() == bundle.fingerprint()
    other = VersionBundle(
        agent=ComponentVersion("agent", "builtin:supervisor"),
        model=ComponentVersion("model", "scripted-policy-v1"),
        benchmark=ComponentVersion("benchmark", "react_basic", "1.0"),
        dataset=ComponentVersion("dataset", "1.0.0", "abc123"),
        evaluator=ComponentVersion("evaluator", "1.x", "task_checks"))
    assert bundle.fingerprint() != other.fingerprint()
    assert set(bundle.to_dict()) == {"agent", "model", "harness", "benchmark",
                                     "dataset", "evaluator", "prompt", "environment"}

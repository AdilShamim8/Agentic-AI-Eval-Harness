"""Tool unit tests — correctness, errors, and safety properties."""
import pytest

from agent_eval_harness.agents import tools as t


@pytest.mark.parametrize("expr,expected", [
    ("2 + 3", 5), ("10 / 4", 2.5), ("23 * 47 + 11", 1092),
    ("0 * 999 + 19", 19), ("3 - 87 - 41", -125), ("9999 * 9999", 99980001),
    ("0 / 7", 0), ("2 ** 10", 1024), ("(2 + 3) * 4", 20), ("-5 + 3", -2),
])
def test_calculator_correct(expr, expected):
    res = t.calculator({"expression": expr})
    assert res.ok and res.value["value"] == expected


@pytest.mark.parametrize("expr", [
    "__import__('os')", "open('/etc/passwd')", "1 +", "1 / 0",
    "2 ** 9999", "abc", "", "1;2", "exec('x')",
])
def test_calculator_rejects_unsafe(expr):
    res = t.calculator({"expression": expr})
    assert not res.ok and res.error


def test_calculator_int_normalization():
    assert t.calculator({"expression": "10 / 2"}).value["value"] == 5


def test_search_relevance():
    res = t.knowledge_search({"query": "maximum vacation carryover",
                              "corpus": "employee_handbook"})
    assert res.ok
    top = res.value["results"][0]
    assert top["doc_id"] == "HB-1"
    assert "5 days" in top["snippet"]


def test_search_unknown_corpus_and_no_match():
    assert not t.knowledge_search({"query": "x", "corpus: ": ""}.get("query", "x") and {"query": "x", "corpus": "nope"}).ok
    res = t.knowledge_search({"query": "zzzz qq", "corpus": "employee_handbook"})
    assert not res.ok


def test_data_calc_ops():
    assert t.data_calc({"values": [1, 2, 3], "op": "sum"}).value["value"] == 6
    assert t.data_calc({"values": [1, 2, 3], "op": "mean"}).value["value"] == 2
    assert t.data_calc({"values": [3, 1, 2], "op": "median"}).value["value"] == 2
    assert t.data_calc({"values": [1, 2], "op": "range"}).value["value"] == 1
    assert not t.data_calc({"values": "notalist", "op": "sum"}).ok
    assert not t.data_calc({"values": [1], "op": "bogus"}).ok
    assert not t.data_calc({"values": ["a"], "op": "sum"}).ok


def test_text_tools():
    assert t.text_transform({"text": "abc", "op": "upper"}).value["result"] == "ABC"
    assert t.text_transform({"text": "abc", "op": "reverse"}).value["result"] == "cba"
    assert t.text_transform({"text": "abc", "op": "nope"}).error
    stats = t.text_stats({"text": "one two three."}).value
    assert stats["words"] == 3 and stats["sentences"] == 1
    summ = t.summarize({"text": "A. B. C.", "max_sentences": 2}).value
    assert summ["summary"] == "A. B."


def test_store_roundtrip_and_isolation():
    t.reset_case_store()
    assert t.store_set({"key": "k", "value": 42}).ok
    assert t.store_get({"key": "k"}).value["value"] == 42
    assert not t.store_get({"key": "missing"}).ok
    t.reset_case_store()
    assert not t.store_get({"key": "k"}).ok  # per-case isolation


def test_sim_web_fixture_only():
    ok = t.sim_web_get({"url": "fixture://reports/q3"})
    assert ok.ok and "4.2 million" in ok.value["content"]
    assert not t.sim_web_get({"url": "http://evil.example.com"}).ok
    assert not t.sim_web_get({"url": "fixture://nope"}).ok


def test_tool_specs_validate_args():
    spec = t.TOOLS["calculator"]
    assert spec.validate_args({"expression": "1+1"}) == ""
    assert "missing" in spec.validate_args({})
    assert "must be str" in spec.validate_args({"expression": 5})
    assert "unknown argument" in spec.validate_args({"expression": "1", "x": 2})


def test_all_tools_registered():
    for name in ("calculator", "knowledge_search", "text_stats", "text_transform",
                 "summarize", "data_calc", "store_set", "store_get", "clock_now",
                 "sim_web_get"):
        assert name in t.TOOLS

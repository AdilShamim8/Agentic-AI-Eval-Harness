"""Task-understanding parser unit tests (every dataset family)."""
from agent_eval_harness.agents.model import understand_task


def test_calc_family():
    u = understand_task("Compute 23 * 47 + 11 using the calculator and report the final value.")
    assert [(a.kind, a.tool) for a in u.actions] == [("tool", "calculator")]
    assert u.actions[0].args["expression"] == "23 * 47 + 11"


def test_search_family():
    u = understand_task("What is the maximum vacation carryover? Search the employee_handbook corpus.")
    assert u.actions[0].tool == "knowledge_search"
    assert u.actions[0].args["corpus"] == "employee_handbook"
    assert u.actions[0].args["query"] == "the maximum vacation carryover"


def test_transform_stats_summarize_families():
    u = understand_task("Apply uppercase to the text: quarterly report")
    assert u.actions[0].tool == "text_transform" and u.actions[0].args["text"] == "quarterly report"
    u = understand_task("How many words are in the following text: one two three")
    assert u.actions[0].tool == "text_stats"
    u = understand_task("Summarize the following text in 2 sentences: A. B. C.")
    assert u.actions[0].tool == "summarize" and u.actions[0].args["max_sentences"] == 2


def test_store_chain_family():
    u = understand_task("Save the value 42 under the key 'note.value'. Then read back the key 'note.value' and report its value.")
    assert [a.tool for a in u.actions] == ["store_set", "store_get"]
    assert u.actions[0].args["value"] == 42


def test_multistep_family():
    u = understand_task("First compute 6 * 7 using the calculator. Then apply uppercase to the text status report. Finally, report both values.")
    assert [a.tool for a in u.actions] == ["calculator", "text_transform"]
    assert u.compose == "all"


def test_compound_handle_family():
    u = understand_task("Handle this request: compute 9 * 7 using the calculator; and look up the probation length in the employee_handbook corpus. Combine both results in your reply.")
    assert [a.tool for a in u.actions] == ["calculator", "knowledge_search"]
    assert u.compose == "all"


def test_route_family():
    u = understand_task("Route this through the team: retrieve the Aurora Laptop 16 battery capacity from the product_specs corpus, then compute 4 * 25 using the calculator, then report both.")
    assert [a.tool for a in u.actions] == ["knowledge_search", "calculator"]


def test_map_reduce_lookup_family():
    u = understand_task("For each of {Springfield, Riverton, Highland}, look up its population in the city_data corpus, then compute the sum of the results and report the total.")
    assert [a.tool for a in u.actions] == ["knowledge_search"] * 3
    assert u.aggregate_op == "sum" and u.concept == "population"
    assert u.actions[0].args["query"] == "Springfield population"


def test_map_reduce_calc_family():
    u = understand_task("For each of {12 * 4, 3 * 9}, compute the value, then compute the mean of the results and report it.")
    assert [a.tool for a in u.actions] == ["calculator", "calculator"]
    assert u.aggregate_op == "mean"


def test_assumption_marker_inserts_think_step():
    u = understand_task("What is the per-diem meal cap (domestic or international, unclear)? Assume the intended meaning and answer. Search the employee_handbook corpus.")
    assert u.actions[0].kind == "assume"
    assert u.actions[1].tool == "knowledge_search"


def test_unparseable_returns_empty():
    u = understand_task("Draw me a picture of a sunset.")
    assert u.actions == []

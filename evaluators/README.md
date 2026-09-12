# Evaluators (release copies)

Reference copies of the evaluator contract surface. The canonical source is
`source/src/agent_eval_harness/evaluators/` (importable as
`agent_eval_harness.evaluators`). These copies exist so reviewers can read the
evaluation logic without walking the package tree.

- `base.py` — Evaluator protocol
- `deterministic_outcome.py` / `deterministic_tools.py` — deterministic checks
- `trajectory_behavior.py` — trajectory + behavioral evaluators
- `llm_judge.py` — rubric + live judge backends (versioned prompts in ../prompts/)
- `registry.py` — name -> factory registry (20 evaluators)

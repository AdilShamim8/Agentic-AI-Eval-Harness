# Interview narrative — 90-second version

"We built 'pytest for agents' end to end. Five agent patterns run through a
permissioned tool gateway with ablatable retry, verification, and context
optimization; 280 machine-verified golden cases across six difficulty
categories; twenty evaluators from exact-match to a calibrated LLM judge;
regression gates that actually fail CI.

Three moments I'd highlight: first, our ablation study initially returned
zero deltas everywhere — instead of shipping 'no effect', I treated it as a
bug report and found the benchmark config was silently overriding the
experiment flag. Second, calibrating the judge against hand labels gave
kappa 0.08 — 24 false negatives from verbosity bias — we published the
failing number, fixed the rubric semantics, and re-measured at 1.0. Third,
my own reproducibility test caught process-salted hash seeding that made
datasets non-deterministic; it's now a CI assertion.

The philosophy: evaluation infrastructure must be more trustworthy than the
thing it measures — deterministic by construction, statistically honest with
Wilson intervals and McNemar, fail-closed gates, and 'Not measured yet' as
an explicit status instead of an embarrassment."

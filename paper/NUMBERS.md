# Where every number in the paper comes from

Paths are under `results/`. Rates are rounded from the stored values; intervals are `ci95`.

| Number in the paper | File | Key |
|---|---|---|
| 5,922 candidates, 2,301 included, 2,267 Claude Code, 34 Codex | frame.json | `candidates`, `included`, `by_reason.*:included` |
| 2,443 no calls or reports, 116 sandboxes, 1,054 private, 8 after cutoff | frame.json | `by_reason.*` (summed across harnesses) |
| 7,169 reported turns, 88,379 tool calls | frame.json | `included_turns`, `included_calls` |
| 400 turns, 2,082 claims, 5.21 per turn | benchmark.json | `labels.turns_labelled`, `labels.claims`, `labels.claims_per_turn` |
| 1,806 supported, 271 unbacked, 5 contradicted | benchmark.json | `labels.verdicts` |
| 13.3% (11.3 to 15.4), 293 sessions | benchmark.json | `labels.not_supported` |
| 13.4% dev, 13.1% test | benchmark.json | `labels.by_split.dev.rate`, `labels.by_split.test.rate` |
| basis: 27 stale, 4 direct, 187 none | benchmark.json | `labels.not_supported_basis` |
| Table 1 family rows | benchmark.json | `labels.by_family.<family>` |
| Table 1 model rows | benchmark.json | `labels.by_model.<model>` |
| Table 1 length rows (5.1%, 14.4%, 13.1%, 20.4%) | benchmark.json | `labels.by_length.<bucket>` |
| 2,000 resamples, seed 7 | benchmark.json | `bootstrap` |
| A 890, B 880, matched 786, F1 0.888, agreement 94.8%, kappa 0.739, flag kappa 0.757 | validity_agreement.json | `claims_A`, `claims_B`, `matched`, `claim_set_f1`, `verdict_agreement`, `verdict_kappa`, `flag_kappa` |
| 745 agreed, 239 disputes, 205 claims, 34 not | adjudication.json | `agreed`, `disputes`, `ruled_claim`, `ruled_not_claim` |
| 40 audited, 37 agreed, 3 reversed, seed 11 | adjudication_audit.json | `audited`, `author_agrees`, `author_reversed`, `audit_seed` |
| 950 gold claims, 175 turns | validity_test.json | `gold_claims`, `turns` |
| Rules, regex: 0.75 / 0.15 / kappa -0.0003 / 0.045 / 0.024; 3 caught, 121 missed, 63 false | validity_test.json | `extraction_precision`, `extraction_recall`, `verdict_kappa_on_matched`, `end_to_end_flag_*`, `flag_counts` |
| Rules, LLM: 0.76 / 0.73 / kappa 0.003 / 0.083 / 0.153; 19 true, 210 false; 137 and 60 | validity_test_llm.json | same keys; `confusion_sys_by_gold.unbacked\|supported`, `supported\|unbacked` |
| Judge H: 0.72 / 0.88 / 0.45 / 0.307 / 0.524; 174 turns, 947 gold | validity_judge_H.json | same keys |
| Judge S: 0.83 / 0.81 / 0.52 / 0.557 / 0.315; matched precision 0.81 | validity_judge_S.json | same keys; `checker_flag_precision_on_matched` |
| Dev flag F1 0.088 to 0.201, 15 rounds | `.hillclimb/results.tsv` (untracked; rounds 0 and best kept round) | `score` column |
| Hook 7.2 ms p50, 18.2 p90, 43.1 p99; 16.0% of last turns flagged; arm64, Python 3.14 | hook_cost.json | `ms_p50`, `ms_p90`, `ms_p99`, `last_turn_flagged_share`, `machine`, `python` |
| Judge and rater time and API-equivalent cost | judge_cost.json | `<rater>.seconds_median`, `seconds_p90`, `api_equivalent_usd_mean` |
| 2.1 ms live catch | docs/live-hook/ (recorded hook run) | |
| v0 pilot: 5 sessions, 324 claims | archive/v0/README.md | |

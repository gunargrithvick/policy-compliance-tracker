# Retrieval Component Ablation

The ablation was run on all 200 cases in `research/evaluation_cases.json` on 2026-08-17. Each variant used the same candidate-source corpus and was run in a fresh worker process.

| Variant | Precision | Recall | F1 | Hit Rate | Error Cases |
|---|---:|---:|---:|---:|---:|
| Semantic Only | 0.703 | 0.602 | 0.630 | 0.587 | 108 |
| Semantic + Lexical Overlap | 0.779 | 0.861 | 0.784 | 0.728 | 87 |
| Semantic + Lexical + Source-Role Scoring | 0.779 | 0.861 | 0.784 | 0.728 | 87 |
| Full Production Hybrid Selector | 0.983 | 0.991 | 0.985 | 0.979 | 8 |

## Interpretation

Lexical overlap improves both recall and F1 over direct semantic retrieval. Source-role scoring does not change the aggregate source selections for the intermediate variant on this particular corpus, although it remains part of the production scoring logic. The full production selector, together with the evidence-backed source-topic vocabulary, reaches the strongest result while retaining supported policy/control evidence and rejecting weak matches. The latest run recorded eight full-hybrid retrieval errors.

The result is an ablation, not a claim that every component independently improves every corpus. The dataset is project-specific, the labels are project-maintained pending compliance review, and the eight full-hybrid failures remain included as observed limitations.

Generated artifacts:

- `research/results/retrieval_ablation_20260817T130545Z.json`
- `research/results/retrieval_ablation_cases_20260817T130545Z.csv`

# Reproducible Research-Gap Evaluation

This tracked summary records the latest paper-ready evaluation snapshot. The
timestamped JSON and CSV artifacts are generated locally in `research/results/`
and are intentionally ignored by Git; run `python research/run_gap_suite.py`
to recreate them.

## Results snapshot

Generated on 2026-09-08 from the current project code and evaluation corpus.

| Evaluation | Result |
|---|---:|
| Retrieval cases | 200 |
| Hybrid retrieval mean F1 | 0.985 |
| Full ablation cases | 200 |
| End-to-end mapping accuracy | 0.951 |
| End-to-end obligation coverage | 0.892 |
| ClaimRAG legal evidence-hit rate | 0.114 |
| ClaimRAG full-pipeline cases | 149 |
| Pipeline tracker-schema completion | 1.000 |
| Pipeline evidence-chain completion | 1.000 |
| Candidate policy-alignment rate | 1.000 |
| Candidate control-alignment rate | 0.725 |
| Human-review gate rate | 0.544 |
| Complete automated test suite | 52 passed |

## Interpretation and limits

The implementation demonstrates a reproducible path from legal text to
structured obligations, evidence records, candidate policy/control
relationships, mapping status, and human-review escalation. Policy/control
relationships remain candidate alignments; these results do not claim legal
compliance certification or externally validated organization-specific
mappings.

The ClaimRAG-LAW benchmark supplies legal retrieval and claim labels, but not
gold labels for organization-specific policies or controls. The project's 200
evaluation cases and policy/control mappings are project-maintained and should
be reported as such.

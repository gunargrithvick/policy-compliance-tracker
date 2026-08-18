# Paper Outline

## Proposed Title

Policy Compliance Tracker: Evidence-Grounded Regulatory Change Monitoring and Policy Impact Mapping

## Abstract Focus

Describe the problem, the local compliance-monitoring workflow, the RAG and agentic design, the policy impact tracker output, and the controlled retrieval evaluation. Do not claim universal regulatory coverage.

## Research Contribution

The project contribution is an auditable local workflow that connects regulatory text to retrieved internal policy/control evidence, extracts explicit obligations, records evidence and retrieval diagnostics, and converts the result into a duplicate-aware tracker record with ownership, priority, review gates, status, alerts, and audit history.

## Evaluation Protocol

Use `research/evaluation_cases.json` as the labelled query set. Compare the project's hybrid retrieval with `semantic_top_k` and `keyword_baseline` using precision, recall, F1, MRR, hit rate, context relevance, cold-start latency, warm latency, and case-level error categories. Run `research/run_ablation.py` for the cumulative semantic, lexical, source-role, and full-hybrid component comparison. Run `research/evaluate_end_to_end.py` to measure policy precision/recall/F1, control precision/recall/F1, obligation coverage, mapping accuracy, and tracker latency. Report the corpus, embedding model, retrieval settings, evidence-quality threshold, label-review status, and exact commands.

## Limitations to State

- The evaluation corpus is small and bundled with the project.
- Expected-source, policy, control, and obligation labels are project-maintained and pending independent review.
- End-to-end mapping scores are only as reliable as the reviewed labels and the bundled policy/control corpus.
- Retrieval quality does not by itself prove legal correctness.
- Structured obligations and evidence records are extraction aids, not legal advice.
- Critical tracker items remain subject to human approval.
- Regulatory feeds may fail because a source is unavailable, blocks automated requests, or does not expose PDF links.
- The dashboard supports human review; it does not replace legal or compliance decisions.

## Related Work

Use `research/related_work.md` for the project-specific discussion of RAG, agentic workflows, and legal-language evaluation.

Use `research/ablation_results_200.md` when reporting the component contribution results. State explicitly that source-role scoring did not change aggregate selections on this project-specific corpus, while the full selector improved performance through its evidence gates and companion-source selection.

When reporting review counts, distinguish the latest Hybrid-RAG retrieval result's 9 source-retrieval errors from the latest manual-review artifact's 20 broader manual-review flags. The latter includes case-level mapping, evidence-quality, and review-gate checks, so the two counts are not contradictory and must not be compared as identical metrics.

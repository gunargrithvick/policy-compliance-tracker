# Paper Outline

## Proposed Title

Policy Compliance Tracker: Evidence-Grounded Regulatory Change Monitoring and Policy Impact Mapping

## Abstract Focus

Describe the problem, the local compliance-monitoring workflow, the RAG and agentic design, the policy impact tracker output, and the controlled retrieval evaluation. Do not claim universal regulatory coverage.

## Research Contribution

The project contribution is a reproducible, auditable workflow that connects
regulatory text to retrieved internal policy/control evidence, extracts
explicit obligations, records evidence and retrieval diagnostics, and converts
the result into a duplicate-aware tracker record with ownership, priority,
review gates, status, alerts, and audit history. The public-benchmark extension
tests whether legal passages can traverse this complete workflow in memory,
while preserving the distinction between source-grounded evidence and
organization-specific candidate mappings.

The research gap is therefore addressed as a systems-and-evaluation gap: the
project connects legal evidence, structured obligations, policy/control impact,
remediation tracking, and human review in one reproducible experiment. It does
not claim that a public legal benchmark validates company-specific control
correctness.

## Evaluation Protocol

Use `research/evaluation_cases.json` as the labelled query set. Compare the project's hybrid retrieval with `semantic_top_k` and `keyword_baseline` using precision, recall, F1, MRR, hit rate, context relevance, cold-start latency, warm latency, and case-level error categories. Run `research/run_ablation.py` for the cumulative semantic, lexical, source-role, and full-hybrid component comparison. Run `research/evaluate_end_to_end.py` to measure policy precision/recall/F1, control precision/recall/F1, obligation coverage, mapping accuracy, and tracker latency. Report the corpus, embedding model, retrieval settings, evidence-quality threshold, label-review status, and exact commands.

Run `python research/evaluate_claimrag.py` as a separate external legal-benchmark
track. Report the pinned revision and actual downloaded record counts. Do not
combine ClaimRAG-LAW legal-evidence results with project-specific policy/control
mapping scores.

Run `python research/evaluate_claimrag_pipeline.py` to pass every pinned legal
passage through the in-memory obligation, evidence, candidate mapping,
validation, and review-gate workflow. Report tracker-schema completion,
evidence-chain completion, candidate policy/control alignment rates, and review
gate rate as structural pipeline metrics, not gold-label accuracy.

For the complete reproducible run, use:

```powershell
python research/run_gap_suite.py
```

The latest consolidated results are recorded in
`research/gap_evaluation_report.md`.

## Limitations to State

- The evaluation corpus is small and bundled with the project.
- Expected-source, policy, control, and obligation labels are project-maintained and pending independent review.
- End-to-end mapping scores are only as reliable as the reviewed labels and the bundled policy/control corpus.
- Retrieval quality does not by itself prove legal correctness.
- Structured obligations and evidence records are extraction aids, not legal advice.
- Critical tracker items remain subject to human approval.
- Regulatory feed ingestion uses retries, configured official fallback URLs, and cached feed pages. A wholly unknown domain change remains an operational limitation because it requires a new trusted source URL.
- The dashboard supports human review; it does not replace legal or compliance decisions.
- ClaimRAG-LAW supplies legal retrieval and claim labels, but not gold labels for organization-specific policy/control mappings.
- The public-benchmark pipeline results measure structural completion and evidence chaining, not legal correctness of every extracted obligation.

## Related Work

Use `research/related_work.md` for the project-specific discussion of RAG, agentic workflows, and legal-language evaluation.

Use `research/ablation_results_200.md` when reporting the component contribution results. State explicitly that source-role scoring did not change aggregate selections on this project-specific corpus, while the full selector improved performance through its evidence gates and companion-source selection.

When reporting review counts, distinguish the latest Hybrid-RAG retrieval result's 9 source-retrieval errors from the latest manual-review artifact's 20 broader manual-review flags. The latter includes case-level mapping, evidence-quality, and review-gate checks, so the two counts are not contradictory and must not be compared as identical metrics.

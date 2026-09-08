# Research-Gap Phase Status

Updated after the reproducible suite run on 2026-09-08.

## Research gap being addressed

Existing work commonly evaluates only one part of compliance automation, such
as legal retrieval, obligation extraction, or RAG answer quality. This project
addresses the missing end-to-end connection:

`regulation -> obligation -> evidence -> policy candidate -> control candidate -> gap/action -> auditable tracker -> human review`

The project claims a reproducible workflow and evaluation protocol. It does
not claim legal certification or externally validated organization-specific
policy/control mappings.

## Phase checklist

| Phase | Status | Evidence |
|---|---|---|
| 1. Define the research problem | Complete | `research/paper_outline.md`, `research/validation_protocol.md` |
| 2. Prepare trusted source material | Complete | `data/regulations/`, `data/policies/`, `data/controls/`, `data/frameworks/`, `data/validation/validation_profile.json` |
| 3. Ingest and validate documents | Complete | `src/policy_compliance_tracker/retrieval/ingest.py`, ingestion tests, Chroma index |
| 4. Implement hybrid retrieval | Complete | `src/policy_compliance_tracker/retrieval/`, `research/run_experiments.py`, `research/run_ablation.py` |
| 5. Extract structured obligations | Complete | `obligations_structured` tracker field and source-span metrics |
| 6. Map obligations to policies and controls | Complete as candidate mapping | `mapping_graph`, `mapping_validation`, `candidate_alignment` status |
| 7. Add auditability and human review | Complete | evidence records, review gates, tracker schema, exports |
| 8. Evaluate with public validated data | Complete | `research/evaluate_claimrag.py`, `research/evaluate_claimrag_pipeline.py` |
| 9. Perform ablation and error analysis | Complete | `research/ablation_results_200.md`, `research/hybrid_failure_analysis_200.md`, generated result JSON files |
| 10. Produce the final research contribution | Complete as a project artifact | `research/final_paper_draft.md`, consolidated results report, limitations, and reproducibility command |

## Latest measured evidence

The latest consolidated report is:

`research/gap_evaluation_report.md`

It records:

- Hybrid retrieval mean F1: `0.985`
- End-to-end mapping accuracy on the project demonstration set: `0.951`
- End-to-end obligation coverage: `0.892`
- ClaimRAG full-pipeline cases: `149`
- Full-pipeline tracker-schema completion: `1.000`
- Full-pipeline evidence-chain completion: `1.000`
- Candidate policy-alignment rate: `1.000`
- Candidate control-alignment rate: `0.725`
- Complete test suite: `47 passed`

## Final paper checklist

1. Use the generated report as the results source.
2. Report project-maintained labels separately from public benchmark labels.
3. Describe policy/control results as candidate alignments unless an official
   crosswalk supports a relationship.
4. Include failure cases and the human-review gate rate.
5. State that the system supports compliance analysis and traceability; it does
   not provide legal advice, certification, or organization approval.

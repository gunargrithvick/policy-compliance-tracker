# Research Evaluation Package

This folder contains the reproducible evaluation materials for the Policy Compliance Tracker paper.

The current phase-by-phase implementation status is recorded in
`research/phase_status.md`.

The paper-ready project draft is in `research/final_paper_draft.md`.

## Research Questions

1. Does the project's hybrid RAG retrieval identify the expected policy and control sources for compliance queries?
2. How does hybrid retrieval compare with a simple keyword-retrieval baseline?
3. Which hybrid retrieval components contribute to the observed performance?
4. Which query categories produce missed or unexpected sources?
5. What retrieval latency is observed for each method?
6. Does evidence quality identify cases that should be escalated to human review?

## Dataset

`evaluation_cases.json` contains 200 labelled queries. The original 30 cases are retained as a frozen baseline, and 170 additional cases cover security, privacy, continuity, data governance, financial-crime, multi-policy, and no-match scenarios. Each case records its category, expected source documents, expected policies, expected control IDs, and expected obligation terms. The labels are based on the bundled policy and control corpus:

- `data/policies/Data_Privacy_Policy.pdf`
- `data/policies/Information_Security_Policy.pdf`
- `data/policies/Business_Continuity_Policy.pdf`
- `data/policies/Data_Governance_Policy.pdf`
- `data/policies/Financial_Crime_Policy.pdf`
- `data/controls/Core_Control_Matrix.pdf`
- `data/controls/Supplemental_Control_Matrix.pdf`

The dataset is a project-specific evaluation set. Its `label_status` is `project-maintained-pending-human-review`; the project must not describe these labels as independently validated until a compliance reviewer confirms them using `research/label_review.md`.

The primary public validation profile is documented in `data/validation/validation_profile.json`. It uses the downloaded GDPR regulation and NIST Privacy Framework Core 1.0 as the generic research scope. This public profile does not convert the existing project-maintained 200-case mapping labels into expert-validated labels; it supplies authoritative source material and a stable control vocabulary.

## Methods

### Hybrid RAG

The project retrieves candidate passages from Chroma using the `all-MiniLM-L6-v2` embeddings, then applies lexical overlap, vector affinity, and source-role selection logic. Query-complexity metadata is recorded in the application retrieval diagnostics. Low-evidence tracker records are marked for review instead of being treated as fully automatic decisions.

### Semantic Top-K Comparison

This comparison uses Chroma's direct semantic top-k ordering without the lexical reranking and source-role selection logic. It isolates the contribution of the hybrid selector.

### Component Ablation

The controlled component ablation runs the same 200 cases through four cumulative stages:

1. `semantic_only`: direct embedding similarity.
2. `semantic_plus_lexical`: semantic candidate scores plus lexical overlap.
3. `semantic_lexical_role`: the previous stage plus policy/control source-role scoring.
4. `full_hybrid`: the unchanged production selector, including its evidence gates and companion-source selection.

Run it after building the Chroma index:

```powershell
python research/run_ablation.py
```

The timestamped JSON and CSV outputs are written to `research/results/`. This experiment describes component contribution; it does not change the production retrieval behavior or tune the system to reach a target score.

The latest 200-case interpretation is recorded in `research/ablation_results_200.md`.

### Keyword Baseline

The baseline tokenizes the query and each complete source document, counts meaningful token overlap, and returns the top two non-zero matches. It does not use embeddings, expected labels, or the RAG selector.

## Metrics

- **Precision**: expected sources divided by returned sources.
- **Recall**: expected sources returned divided by expected sources.
- **F1**: harmonic mean of source precision and source recall.
- **MRR**: reciprocal rank of the first expected source in the returned ordering.
- **Hit rate**: Jaccard overlap between expected and returned source sets.
- **Context relevance**: expected terms found in returned context.
- **Latency**: wall-clock retrieval time in milliseconds.
- **Cold-start latency**: the first retrieval latency in a fresh process.
- **Warm latency**: latency after model and index initialization.
- **Obligation field completeness**: populated actor, action, target, condition, deadline, and source-span fields for explicit obligation cases.
- **Source-span coverage**: explicit obligation claims whose source span is present in the supplied regulation evidence. Short retrieval queries that do not contain an explicit obligation are reported as non-obligation fallbacks and excluded from this denominator.
- **Mapping evidence coverage**: policy/control mapping edges linked to evidence records.
- **Unsupported-claim rate**: explicit obligation claims that have no verified source span; query-only fallbacks are excluded.

The evidence tiers and reporting rules are defined in `research/validation_protocol.md`. Candidate alignments are not counted as official crosswalks.

The runner also records missing sources, unexpected sources, error type, category, and per-case rankings for error analysis. Each retrieval method runs in its own worker process so its first case is a genuine method-specific cold start; later cases are warm measurements. The tracker stores structured obligations, evidence excerpts, retrieval diagnostics, review-gate metadata, and regulation-policy-control relationship edges.

## End-to-End Mapping Evaluation

Run the mapping evaluation separately after installing dependencies:

```powershell
python research/evaluate_end_to_end.py
```

This compares expected policies, controls, and obligation terms with the generated tracker record. It reports policy precision/recall/F1, control precision/recall/F1, obligation coverage, mapping accuracy, and latency. These results measure the deterministic project path and do not establish legal correctness.

## Open Legal Benchmark Evaluation

Run the separate legal-evidence benchmark after rebuilding the local index:

```powershell
python research/evaluate_claimrag.py
```

This downloads the pinned ClaimRAG-LAW GDPR files, verifies their SHA-256 hashes,
and evaluates whether local GDPR retrieval reaches the published evidence chunk.
It also records the benchmark's published claim-label distribution. It does not
validate this project's organization-specific policy/control mappings; those
remain `candidate_alignment` results unless an official crosswalk supports them.

ClaimRAG-LAW is used under CC BY 4.0. The attribution notice is stored in
`data/benchmarks/claimrag_law/README.md`.

To test the research gap's complete workflow, run the benchmark passages
through the project tracker in memory:

```powershell
python research/evaluate_claimrag_pipeline.py
```

This second evaluation measures end-to-end structural completion: obligation
extraction, source-grounded evidence, candidate policy/control alignment,
mapping-validation status, and the human-review gate. It does not persist
benchmark cases and does not treat project policy/control matches as gold
labels. A `candidate_alignment` status is the expected safe result when no
official crosswalk or organization-specific approval is supplied.

Check the labels against the bundled source files:

```powershell
python research/validate_labels.py
```

The validator checks source consistency for expected files, policies, and controls, and checks obligation terms against the query or expected source text. It separately reports query-derived terms that are not present in the expected policy/control sources. It does not replace independent compliance-reviewer validation.

## Run the Experiment

To run the complete research suite and create one paper-ready report:

```powershell
python research/run_gap_suite.py
```

This runs the retrieval comparison, component ablation, labelled end-to-end
mapping evaluation, ClaimRAG legal-evidence evaluation, ClaimRAG full-pipeline
evaluation, and the complete test suite. The consolidated Markdown report is
written to `research/results/`; the tracked paper-ready results snapshot is
[`gap_evaluation_report.md`](gap_evaluation_report.md).

From the repository root:

```powershell
python -m policy_compliance_tracker.retrieval.ingest
python research/run_experiments.py
```

The runner writes timestamped JSON and CSV files to `research/results/`. These generated outputs are ignored by Git. Use the tracked [`gap_evaluation_report.md`](gap_evaluation_report.md) for the paper's results snapshot, the JSON summary for detailed metrics, and the CSV case rows for error analysis. The comparison includes `rag_hybrid`, `semantic_top_k`, and `keyword_baseline`, with method-specific cold-start and warm-run latency reporting. The separate component ablation is run with `python research/run_ablation.py`. Rebuilding the index removes only the Chroma collection and preserves the SQLite tracker database.

The 200-case Hybrid-RAG error analysis is documented in `research/hybrid_failure_analysis_200.md`. The listed failures are retained as observed limitations and are not removed to improve the aggregate score.

Before making final paper claims, create a new `final_manual_review_*.json` artifact for all 200 cases and the required edge cases. It should record the returned policies, controls, priorities, evidence quality, review gates, and failure flags; older manual-review artifacts must not be presented as 200-case results.

Generate the current artifact with:

```powershell
python research/generate_manual_review.py
```

Report the counts separately: the retrieval experiment's `error_cases` is the number of source-retrieval errors, while the manual-review artifact's `manual_review_flag_count` (also retained as `manual_failure_count` for compatibility) counts broader case-level mapping, evidence, and review flags. These are different scopes and must not be presented as the same metric.

## Reporting Rules

- Report the observed values; do not tune the implementation to force a target percentage.
- State that the dataset is project-specific and small.
- Report the baseline and RAG under the same candidate-source set.
- Include missed-source and unexpected-source cases in the error analysis.
- Separate retrieval metrics from end-to-end agent quality.
- Treat tracker priorities, owners, and policy changes as recommendations requiring compliance review.

## Paper Structure

Use the following project-specific sections in the paper:

1. Problem and motivation
2. Related work on legal/compliance NLP, RAG, and agentic workflows
3. System architecture and implementation
4. Structured obligation and evidence model
5. Evaluation dataset and protocol
6. RAG-versus-keyword results
7. Error analysis and limitations
8. Conclusion and future work

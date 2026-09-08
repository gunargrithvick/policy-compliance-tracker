# Policy Compliance Tracker: Evidence-Grounded Regulatory Change Monitoring and Policy Impact Mapping

## Abstract

Regulatory compliance automation is often evaluated as separate components:
legal retrieval, obligation extraction, RAG answer quality, or policy-aware
decision-making. This project presents a reproducible workflow that connects
these stages. The system retrieves regulatory and organizational evidence,
extracts structured obligations, links obligations to candidate policies and
controls, identifies control gaps and policy changes, and stores the result in
an auditable tracker with provenance and human-review gates. The evaluation
combines a 200-case project demonstration set with an openly licensed GDPR
legal-evidence benchmark. On the project set, hybrid retrieval achieves a mean
F1 of 0.985, while the deterministic end-to-end mapping path achieves mean
mapping accuracy of 0.951 and obligation coverage of 0.892. On 149 pinned
public benchmark passages, the full in-memory workflow completes the tracker
schema and evidence chain for every case. These public-benchmark results measure
workflow completion and source evidence chaining; they do not establish the
legal correctness of organization-specific policy/control mappings.

## 1. Research gap and question

Within the 20 reviewed papers, existing work addresses individual parts of the
problem: adaptive retrieval, legal reasoning, obligation extraction, citation
quality, hallucination detection, policy-aware decisions, graph retrieval, or
RAG evaluation. The reviewed set does not present and evaluate one complete
workflow connecting primary regulatory text to structured obligations, evidence,
policy impact, control impact, control gaps, remediation actions, an auditable
tracker, and human-review escalation.

The research question is:

> How can a hybrid, evidence-grounded RAG workflow transform regulatory text
> into structured obligations and traceable policy/control impact records while
> identifying control gaps and escalating uncertain mappings for human review?

## 2. System contribution

The project implements the following chain:

`regulation -> obligation -> evidence -> policy candidate -> control candidate -> gap/action -> tracker -> review`

The tracker records structured obligations, source spans, evidence records,
retrieval diagnostics, mapping graphs, validation status, confidence, priority,
owner, due-date text, policy-change reasoning, and review requirements.

The system distinguishes three important evidence states:

- `source_grounded`: the claim is linked to a supplied regulatory source span.
- `framework_supported`: a relationship is supported by a public framework or
  issuer-provided crosswalk.
- `candidate_alignment`: a plausible policy/control relationship was found by
  project retrieval and rules but is not an official crosswalk.

This distinction prevents a plausible retrieval match from being reported as
legal certification.

## 3. Data and provenance

The project uses:

- Public regulation PDFs, including GDPR and additional demonstration
  regulations.
- Bundled policy PDFs and control-matrix PDFs.
- NIST Privacy Framework Core 1.0 as a public control vocabulary.
- ClaimRAG-LAW GDPR records at a pinned revision with SHA-256 verification.
- A 200-case project demonstration set for policy/control retrieval and
  obligation-field evaluation.

The project demonstration labels are marked
`project-maintained-pending-human-review`. They are not described as
independently expert-validated. ClaimRAG-LAW provides legal retrieval and claim
labels, but it does not provide gold labels for organization-specific policies,
controls, owners, priorities, or remediation actions.

## 4. Method

The retrieval layer combines embedding search, lexical overlap, source-role
selection, evidence thresholds, and query-complexity diagnostics. The analysis
layer extracts explicit obligation fields and preserves the original source
span. The mapping layer selects candidate policies and controls and records
evidence-backed edges. The tracker layer applies review gates when evidence is
weak, mappings are absent, the impact is critical, or a claim cannot be
verified against its source span.

The evaluation has four complementary parts:

1. Retrieval comparison against semantic top-k and keyword baselines.
2. Controlled ablation of semantic, lexical, source-role, and full-hybrid
   retrieval components.
3. End-to-end evaluation on the 200 project cases.
4. Public legal-benchmark evaluation using ClaimRAG-LAW retrieval records and
   a separate in-memory full-pipeline evaluation.

## 5. Results

| Evaluation | Result |
|---|---:|
| Project retrieval cases | 200 |
| Hybrid retrieval precision | 0.983 |
| Hybrid retrieval recall | 0.991 |
| Hybrid retrieval mean F1 | 0.985 |
| Hybrid retrieval mean MRR | 0.875 |
| Semantic top-k mean F1 | 0.639 |
| Keyword baseline mean F1 | 0.318 |
| End-to-end successful cases | 200/200 |
| End-to-end mean mapping accuracy | 0.951 |
| End-to-end mean obligation coverage | 0.892 |
| Explicit-obligation source-span coverage | 1.000 |
| Explicit-obligation unsupported-claim rate | 0.000 |
| ClaimRAG GDPR retrieval cases | 149 |
| ClaimRAG evidence-hit rate at token-overlap threshold 0.5 | 0.114 |
| ClaimRAG full-pipeline obligations extracted | 1,568 |
| Full-pipeline tracker-schema completion | 1.000 |
| Full-pipeline evidence-chain completion | 1.000 |
| Candidate policy-alignment rate | 1.000 |
| Candidate control-alignment rate | 0.725 |
| Full-pipeline human-review gate rate | 0.544 |
| Complete automated test suite | 47 passed |

The low ClaimRAG retrieval evidence-hit rate must be reported honestly. It
shows that the current local GDPR retrieval configuration does not reliably
match the benchmark's published relevant chunks under the selected token
overlap criterion. The separate full-pipeline result shows that the workflow
can process the supplied passages and preserve evidence structure; it does not
cancel or hide the retrieval weakness.

## 6. Findings

The results support three conclusions:

1. Hybrid retrieval is substantially stronger than the tested keyword and
   semantic-only baselines on the project corpus.
2. The project successfully operationalizes the complete evidence-to-tracker
   workflow, including structured obligations, mapping provenance, and review
   escalation.
3. The public legal benchmark exposes a real retrieval limitation and prevents
   the contribution from being presented as universally solved legal RAG.

## 7. Limitations

- Project-specific policy/control labels are not independent gold labels.
- ClaimRAG-LAW does not validate organization-specific policy/control mapping.
- Candidate alignments are not official legal crosswalks.
- Obligation extraction is not legal advice or a substitute for legal review.
- The benchmark pipeline uses the project's deterministic analysis path for
  reproducibility; it is not evidence that an LLM will produce identical
  results.
- The public benchmark and project corpus cover limited jurisdictions and
  document types.
- The retrieved evidence-hit metric uses token overlap and should be
  complemented by stronger legal relevance evaluation in future work.

## 8. Reproduction

From the repository root:

```powershell
python research/run_gap_suite.py
```

This runs retrieval comparison, component ablation, end-to-end mapping,
ClaimRAG legal retrieval, ClaimRAG full-pipeline evaluation, and the complete
test suite. The latest generated report is stored under
`research/gap_evaluation_report.md`.

## 9. Final contribution statement

This project contributes a reproducible, evidence-grounded compliance tracking
workflow that connects regulatory evidence to structured obligations, candidate
policy/control impact, control-gap analysis, remediation tracking, and human
review. Its novelty is the integration and evaluation of this complete chain,
not the invention of a new retrieval algorithm and not a claim of automatic
legal certification.

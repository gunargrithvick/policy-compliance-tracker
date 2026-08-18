# Hybrid RAG Failure Analysis

This review covers the nine Hybrid-RAG cases marked as errors in the latest
200-case retrieval experiment. The evaluation cases remain fixed. A general
source-topic update added phrases already present in the bundled policy and
control documents, and narrowed a broad security match for "suspicious" to
"suspicious activities". No case was removed or relabeled to improve the
aggregate score.

| Case | Observed Result | Reason Classification |
|---|---|---|
| `audit-logging-investigation` | Expected control and security policy returned; Financial Crime policy also returned | Monitoring and investigation vocabulary overlaps with financial-crime escalation language. This remains an over-selection case. |
| `personal-data-processing-scope` | Data Privacy policy returned; Data Governance policy also returned | The broad stored/processed scope overlaps with governance language. This remains a cross-policy precision case. |
| `continuity-02` | Business Continuity policy and Supplemental Control Matrix returned; the expected label lists only the policy | Disaster-recovery wording overlaps with the continuity-testing control. The result exposes a policy/control relevance ambiguity in the project-specific label. |
| `continuity-06` | Business Continuity policy returned; expected control companion missed | Continuity-testing language is present, but the concise control row does not contain the query's results/remediation wording strongly enough. |
| `financial-04` | Financial Crime policy returned; sanctions-screening control companion missed | The policy contains the review-point wording, while the control row is shorter and less specific. |
| `multi-02` | Data Governance policy and control returned; Business Continuity policy missed | The data-classification phrase dominates the multi-domain query, so the continuity policy is not selected. |
| `auth-11` | Information Security policy and Access Review control returned; expected label lists only the policy | Least-privilege wording matches the control matrix as well as the policy. This is a project-specific expected-source ambiguity. |
| `continuity-34` | Business Continuity policy and Supplemental Control Matrix returned; expected label lists only the policy | Continuity test-gap wording matches the control row in addition to the policy's remediation-owner wording. This is a policy/control precision case. |
| `financial-28` | No expected source returned | The query's suspicious-transaction wording remains below the current financial-crime evidence gate. |

These remaining cases are retained as observed limitations. The latest
aggregate result should be reported as measured, not as a target to optimize.

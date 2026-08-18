# Evaluation Label Review

The 200 evaluation cases in `evaluation_cases.json` are project-maintained labels derived from the bundled policy and control documents. The original 30 cases are retained as a frozen baseline, and 170 additional cases cover security, privacy, continuity, data governance, financial crime, multi-policy, and no-match scenarios. These labels are not independent expert validation.

The automated consistency check currently finds all 200 cases structurally consistent: each references existing bundled source files, policy names scoped to those sources, control IDs, and obligation terms supported by the query or expected source text. It separately reports obligation terms that are query-derived rather than present in the expected policy/control sources. This result does not change the pending independent human-review status.

Before using the dataset as formal research evidence, a compliance reviewer should inspect each case and confirm:

1. The expected source documents are sufficient and do not include unrelated documents.
2. The expected policy names match the policy library.
3. The expected control IDs match the control matrix.
4. The expected obligation terms are appropriate for the regulatory query, and any query-derived terms are intentionally distinguished from policy/control evidence.
5. Cases with no expected control are intentionally policy-only cases.

After review, record the reviewer role, review date, decision, and any correction in a separate version-controlled review log. Do not change `label_status` to an independently reviewed value without a real human review.

# Generic compliance validation protocol

## Scope

The primary experiment evaluates GDPR obligation extraction and evidence-grounded mapping to a public privacy-control vocabulary. The project is not evaluating company-specific policy approval or legal certification.

## Evidence tiers

- **Tier 1 — authoritative source:** the regulation text or the NIST Privacy Framework control text.
- **Tier 2 — official crosswalk:** an issuer-provided relationship between a regulation/framework and a control vocabulary.
- **Tier 3 — candidate alignment:** a transparent project rule or retrieval match without an official crosswalk.

Only Tier 1 and Tier 2 evidence may be described as framework-supported. Tier 3 results are useful research outputs but must be reported as candidate mappings.

## Metrics

- Obligation field completeness: actor, action, target, condition, deadline, and source span.
- Source-span grounding: whether each extracted obligation can be located in the supplied regulation text.
- Evidence coverage: proportion of mapped policy/control claims with a linked source record.
- Unsupported-claim rate: proportion of claims without a verified source span or evidence record.
- Policy/control precision, recall, and F1 on the project demonstration set.
- Retrieval precision, recall, F1, MRR, context relevance, and latency.

The existing 200-case file remains a project-maintained demonstration set. It must not be called independently expert-validated. Public benchmark results and framework provenance are reported separately from the project-specific mapping results.

## Open benchmark

ClaimRAG-LAW is used as the open legal benchmark under CC BY 4.0, with its
attribution and license link preserved. The evaluator pins a dataset revision and
records SHA-256 hashes for reproducibility. Its GDPR records validate legal
evidence retrieval and claim labels. They do not provide gold labels for internal
policies, controls, owners, priorities, or remediation actions.

The evaluator reports the actual records in the pinned JSON files. It does not
replace those counts with the dataset README's advertised counts, and it exposes
blank or nonstandard labels as data-quality information.

The full workflow evaluator is separate:

```powershell
python research/evaluate_claimrag_pipeline.py
```

It runs each pinned GDPR passage through the project's in-memory obligation,
evidence, policy/control candidate, validation, and review-gate stages. Its
completion rates describe pipeline behavior, not legal or policy/control
accuracy. Candidate mappings remain Tier 3 unless supported by an official
crosswalk.

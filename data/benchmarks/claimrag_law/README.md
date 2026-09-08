# ClaimRAG-LAW benchmark

Run the reproducible evaluator from the repository root:

```powershell
python research/evaluate_claimrag.py
```

ClaimRAG-LAW is used under the Creative Commons Attribution 4.0 International
(CC BY 4.0) license. No approval request is required, but attribution and the
license link are required:

- Dataset: https://huggingface.co/datasets/SNTSVV/ClaimRAG-LAW
- License: https://creativecommons.org/licenses/by/4.0/

The evaluator downloads the GDPR files to this directory, verifies their hashes,
and records the exact revision in `manifest.json`. The benchmark validates legal
retrieval and claim grounding; it does not provide gold labels for this project's
organization-specific policy/control mappings. Those mappings remain candidate
alignments supported by evidence.

The pinned JSON files are the measured source of truth for reported counts. At
this revision, the GDPR retrieval file contains 149 records and the GDPR claim
file contains 520 claims. The repository README advertises a different retrieval
count, so the evaluator reports the downloaded count and preserves nonstandard or
blank labels instead of silently correcting them.

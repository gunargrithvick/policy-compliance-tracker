# Validation profile

The project uses a generic, public-data profile rather than a company-specific compliance profile.

## Selected sources

- Primary regulation: `data/regulations/EU_GDPR_Regulation.pdf`, downloaded from the official EUR-Lex source listed in `validation_profile.json`.
- Primary control vocabulary: `data/frameworks/NIST_Privacy_Framework_Core_v1.0.pdf`, the final NIST Privacy Framework Core 1.0.
- Supplemental security vocabulary: NIST Cybersecurity Framework 2.0, used as a reference only.

The NIST Privacy Framework is voluntary guidance. It supplies stable public control terminology; it is not itself a law and does not certify that an organization is compliant.

## How validation is reported

The application distinguishes three states:

1. `framework_supported`: the control or relationship is supported by an issuer-provided framework or official crosswalk.
2. `candidate_alignment`: the system found a plausible mapping using its retrieval and topic rules, but no official crosswalk was found.
3. `needs_review`: the source evidence is missing, weak, incomplete, or outside the selected GDPR/privacy scope.

Existing continuity and financial-crime PDFs remain useful demonstration data, but they are not counted as part of the primary GDPR/NIST validation claim.

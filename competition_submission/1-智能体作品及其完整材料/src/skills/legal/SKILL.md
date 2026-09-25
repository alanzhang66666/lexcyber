# Legal Skill Pack v0.2

This pack contains low-risk legal document processing, source-verification, and review-gate skills.

## Scope

- Extract and normalize information from user-provided text and uploaded documents.
- Search the configured private Retrieval Gateway, including a local development corpus.
- Preserve page/paragraph anchors where the input provides them.
- Return warnings when extraction is heuristic or a knowledge base is unavailable.
- Route high-risk requests into a human review queue.

## Non-goals

- No final legal advice or legal conclusion.
- No claim that a citation is authoritative merely because it was parsed or retrieved.
- No automatic determination of liability, crime, enforceability, or litigation outcome.
- No filing, signing, or sending of formal legal documents.

## Review boundary

Outputs involving legal applicability, deadlines, legal characterization, or conflicting sources must be reviewed by a qualified human. Citation verification is only a retrieval match and is not a substitute for source validation.

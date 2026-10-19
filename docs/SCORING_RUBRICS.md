# Scoring and confidence

Rubrics live in `backend/app/scoring/lead.json` and `sourcing.json` and are seeded into PostgreSQL. Admins create new versions through Settings or `POST /api/policies`. Weights must total 100, keys must be unique, and every criterion lists supported signal identifiers. Existing policies and scores have no update/delete endpoint.

| Lead criterion | Points | Sourcing criterion | Points |
|---|---:|---|---:|
| Buyer Type Fit | 20 | Supplier / Producer Relevance | 20 |
| Coffee Portfolio Fit | 20 | Origin & Product Fit | 20 |
| Active Buying Signals | 15 | Active Production / Availability Signals | 15 |
| Digital / Business Activity | 15 | Market Validation | 15 |
| Market & Industry Presence | 10 | Digital / Business Activity | 10 |
| External Coffee Evidence | 10 | Industry / Network Strength | 10 |
| Contactability | 10 | Contactability & Relationship Potential | 10 |

For each criterion: `points = round(weight × count(supported required signals) / count(required signals))`. A signal is supported when a non-conflicting evidence record carries that signal. Confidence is deliberately not multiplied into business fit. Every breakdown records evidence IDs, weights and an explanation. The result retains policy ID, version and an evidence hash. An explicit rescore creates a new result only when policy/evidence differs.

Missing evidence establishes no points but is labelled missing, not negative. There is no separate penalty for a missing website, unavailable Instagram, newly formed business or producer-direct structure.

Bands: 80–100 Priority; 65–79 Strong; 50–64 Additional Research; 35–49 Weak; 0–34 Not Relevant.

## Confidence heuristic

This is an explicit qualitative heuristic, not a calibrated probability. Evidence with confidence below 0.6 or conflicting verification is excluded from the credible-source set.

- INSUFFICIENT: no credible evidence.
- LOW: conflicting sources, limited independent domains, no fresh corroboration, or substantial missing evidence.
- MEDIUM: at least two credible domains, verified/corroborated evidence, a known publication date within 180 days, and at most one declared missing item.
- HIGH: at least three credible domains, corroboration, fresh evidence, a contact source and no declared missing items.

Unknown publication time is UNKNOWN, never automatically stale. Source-domain counts are a proxy for independence; human research must check common ownership and syndication. Provider/model confidence is advisory; production model outputs cannot mark themselves verified.

Scores never approve outreach. LOW/INSUFFICIENT confidence requires the reviewer to record substantive human-research notes before approving an approach. Suppression, duplicate resolution, active candidate status and a human review remain mandatory.

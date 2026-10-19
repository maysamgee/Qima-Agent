# Security controls

- Pydantic v2 validates input, enums and structured AI output. Backend services enforce role checks, workflow prerequisites and optimistic draft versions.
- Local mock authentication is restricted to local/test. Production requires Cognito RS256 signatures, JWKS key lookup, issuer, expiry, access-token use and the exact client ID. Unknown groups have no privileges.
- Browser sign-in uses authorization code + PKCE/state. Tokens remain in the current tab's session storage; no tokens appear in URLs or logs. A hardened BFF/HttpOnly session is a future option for higher-risk deployments. Access-token expiry requires signing in again in V1.
- V1 refuses real-send flags. Gmail and Meta stubs cannot send. Simulated email has stable provider IDs; Instagram only records a human action.
- Approval is tied to a draft version. Edits invalidate approvals; send reloads draft, approval, candidate, suppression and review under row locks.
- Every important business mutation has an audit record. No physical business DELETE endpoints exist. Archive/merge retain source records and history.
- Discovery fetch requires approved HTTPS hosts, no embedded credentials, port 443, all-public DNS results and a pinned IP connection with original-hostname TLS validation. Local/private/link-local/reserved targets and redirects are rejected. Robots exclusions, content types, response-size limits and timeouts are checked.
- Prompt inputs label external material untrusted. Tools cannot send messages, fetch secrets or mutate scoring policy. Duplicate calls are suppressed and unsupported provenance is rejected. Model-produced verification remains unverified outside demo mode.
- Uploads have extension/signature/text checks and a 10 MiB limit. Files use content-addressed storage keys and attachment-only downloads. Office/PDF files are not executed or automatically parsed; no OCR pipeline exists.
- CORS uses exact configured origins, security headers prevent framing/sniffing, production responses use HSTS, and write requests have an application-level per-process limit. Production edge rate limiting and malware scanning are deployment hardening prerequisites for internet-facing intake.
- RDS is private, encrypted and backed up, with TLS required. Application database credentials are loaded from a separate Secrets Manager container. ECS uses task roles. S3 is private, encrypted and versioned; bucket policies require TLS. IAM scopes queue, document-prefix, log and model access.

Application logs use structured, selected fields instead of dumping request bodies, headers, credentials or provider exception strings. Private message contents are stored as business records for review, but are not emitted to logs. Audit notes are intentionally retained business data and require organizational retention/access policy.

Report issues through the repository owner's established private channel. Do not paste credentials, raw private messages or unredacted production logs into a public issue.

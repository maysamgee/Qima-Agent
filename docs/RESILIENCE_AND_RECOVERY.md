# Resilience and recovery

Search creation commits `search_jobs`, all step rows, an audit event and `outbox_events` in the same transaction. A publication failure leaves the event unpublished with its attempt count and error type. The worker republishes pending events on later ticks. Publishing may succeed before the database commit; duplicates are expected and safe.

Local mode polls durable database jobs. SQS mode uses a standard queue with long polling, configurable visibility, heartbeat extension and a redrive DLQ. Messages contain identifiers and schema version only. PostgreSQL advisory locks serialize processing of a job across workers and are released when the connection/process dies.

Each step commits RUNNING before work and COMPLETED/PARTIAL plus checkpoint output after successful work. Restart skips completed steps. The discovery profile is checkpointed before candidate insertion; insertion/evidence and scoring use unique constraints. A partially completed job remains reviewable, with unavailable sources identified.

There is no distributed exactly-once claim. Business effects are idempotent: job request keys, candidate identities, evidence fingerprints, candidate/policy/evidence score keys, draft/version approvals, unique draft-message references, follow-up request keys, reply keys and a unique candidate handoff. Clients must reuse the same `Idempotency-Key` when retrying the same logical request. A changed search with a reused key is rejected.

Repeated failures set FAILED_PERMANENT after the configured maximum job attempts. Local mode leaves the job visible for review. In SQS mode unsuccessful messages are not acknowledged and SQS moves them to the DLQ according to its receive-count policy. Repair the cause, use the administrator's retry endpoint or redrive the corrected message, and monitor for completion. Finished jobs tolerate duplicate redrive messages.

## Follow-up safety

The follow-up row is authoritative. Scheduler only queues its ID. The handler rereads current status, date, last reply, suppression, candidate archive state and latest approach approval. Early delivery remains unacknowledged for later retry. New replies cancel scheduled reminders. A due reminder creates one unapproved draft and never sends automatically.

## Verified tests

Unit tests terminate processing after the deduplication checkpoint, resume it and verify that completed steps were not repeated. Duplicate delivery produces one candidate, three evidence records and one score. Outbox failure/retry and approval invalidation are also covered.

`python scripts/postgres-recovery.py` exercises a separate process against a unique schema in the local Docker PostgreSQL database. It applies actual migrations, commits checkpoints, exits the first process and resumes with duplicate delivery. The isolated schema is retained, never dropped automatically. This prevents the normal running worker from claiming the test job.

External provider reads can repeat if a process dies before a checkpoint commit. A provider call that creates a real external effect would require a dedicated outbox and provider reconciliation; V1 deliberately has no such sending adapter.

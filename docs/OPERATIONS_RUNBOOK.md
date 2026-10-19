# Operations runbook

## Local readiness

1. `docker compose ps`: PostgreSQL should be healthy.
2. `Invoke-RestMethod http://localhost:8000/health/live`: process is alive.
3. `Invoke-RestMethod http://localhost:8000/health/ready`: database and migration table available.
4. System Status shows actual configured mock/AWS modes. Dependency status does not pretend to probe AWS credentials.
5. Create one small search. Check `/api/jobs/{id}` for durable progress. Review `/api/audit` and structured logs using correlation/job IDs.

## Stuck or failed jobs

Check whether the worker is running with the same database and queue provider. Inspect unpublished outbox events and their last error type. Queue transport errors are retried without removing the database job. Running jobs resume after the old process releases its PostgreSQL advisory lock.

For FAILED_PERMANENT jobs, diagnose and fix provider/configuration failures, then use Search Activity → Retry (ADMIN only), or the authenticated retry endpoint. Completed checkpoints remain intact. Do not delete the job to retry it.

In AWS, examine queue age/depth and DLQ alarms. A DLQ message is not proof of business failure by itself; look up its job ID. Redrive after correction; the database idempotency guards tolerate already-finished jobs. Configure alarm actions to send notifications to an approved SNS topic.

## Messaging

Mock messages are visibly labelled simulated. There is no switch that activates real sending: true real-send flags fail validation. If an approval appears stale, refresh, review the current revision and approve it again. Do not patch approval rows manually. For do-not-contact or probable duplicates, resolve the underlying review issue rather than bypassing checks.

## Follow-ups

Use the database record as authority. A cancelled Scheduler notification can arrive late; the handler safely ignores settled records. Early notifications remain available for retry. A reminder creates an unapproved draft only. A new reply cancels outstanding scheduled reminders.

## Deployment and rollback

Run the full checks and review the migration before deployment. Use immutable image tags. The protected workflow runs migrations/policy seeding and waits for task completion before updating services. ECS deployment circuit breakers roll back failed service releases, but do not reverse database migrations. Use additive/compatible migration patterns and an explicit data recovery plan.

RDS has 14-day automated backup retention and point-in-time recovery support configured; S3 retains versions. Restore into an isolated database/bucket and verify integrity before a human-approved cutover. No restores or production failure drills were run without an AWS account.

## Metrics and retention

`/metrics` requires ADMIN and reports persisted job states, audit-event counters, candidate count and historical average score. ECS Container Insights, ALB errors, RDS free storage, SQS age and DLQ alarms cover infrastructure. Tool/model latency and errors appear in audit/structured log metadata. Define organization-specific dashboards, SLOs, alert routing, message retention and audit retention before production.

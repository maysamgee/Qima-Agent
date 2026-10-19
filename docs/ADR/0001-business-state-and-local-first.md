# ADR 0001: Database-owned workflow and local-first delivery

Status: accepted.

Use PostgreSQL for business state and resumable steps, a transactional outbox for queue delivery, and versioned configuration for deterministic scores. A local worker polls the same durable database jobs; AWS workers consume SQS. No Step Functions or additional autonomous agents are needed.

Use synchronous SQLAlchemy with psycopg for simple, explicit transaction boundaries in API threadpool handlers and worker processes. DATABASE_URL values using asyncpg are normalized to the synchronous psycopg driver. Python 3.12 is the baseline.

All external messaging is simulated or manually recorded. Production rejects local authentication, mock discovery and mock AI unless explicitly operating a non-production environment. Bedrock and AWS adapters are tested with stubs; live account checks require supplied configuration.

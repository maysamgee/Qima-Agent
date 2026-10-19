# ADR 0003: Local verification before deployment

Status: accepted.

The project is verified with real local PostgreSQL and an independent worker, plus isolated default unit tests and AWS SDK stubs. A subprocess recovery test uses a unique retained PostgreSQL schema so the normal worker cannot consume its test job. Browser E2E tests preserve demo records and exercise human approval gates.

Frontend and Terraform dependencies have lock files; backend/requirements-tested.txt records the tested Python environment as an optional constraint set. Security auditing is part of CI, and vulnerable test dependencies were upgraded during the build. Deployment is manually dispatched from main, depends on checks and uses a protected GitHub environment with AWS OIDC. No local setup or test command applies Terraform or contacts real prospects.

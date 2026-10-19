# Environment variables

Copy `.env.example` to `.env` once. All values are placeholders or local demo settings. Shell environment variables take precedence. Restart processes after changes.

| Setting | Purpose |
|---|---|
| APP_ENV | local, test, dev or prod |
| AUTH_MODE | local (local/test only) or cognito |
| DATABASE_URL | PostgreSQL SQLAlchemy URL; psycopg is used; asyncpg spelling is normalized |
| DATABASE_SECRET_ARN, DATABASE_HOST, DATABASE_NAME | Load database username/password from Secrets Manager in ECS |
| DATABASE_SSLMODE, DATABASE_SSLROOTCERT | Secrets-based RDS connections use verify-full and the public RDS CA bundle in ECS |
| CORS_ORIGINS | Comma-separated exact frontend origins |
| AWS_PROFILE, AWS_REGION | Local profile/SSO and selected region; omit profile in ECS |
| AI_PROVIDER | mock or bedrock |
| BEDROCK_MODEL_ID | Account-enabled model or supported inference profile ID |
| BEDROCK_INFERENCE_PROFILE_ARN | Optional profile ARN, takes precedence over model ID |
| BEDROCK_TEMPERATURE, BEDROCK_MAX_OUTPUT_TOKENS | Inference settings |
| BEDROCK_MAX_TOOL_ITERATIONS | Maximum plan iterations and tool-call budget |
| BEDROCK_REQUEST_TIMEOUT_SECONDS | AWS model socket read timeout |
| TOOL_TIMEOUT_SECONDS, JOB_TIMEOUT_SECONDS | Per-tool and job research deadlines |
| QUEUE_PROVIDER | local or sqs |
| DISCOVERY_QUEUE_URL, DISCOVERY_DLQ_URL | Development/production queue addresses |
| QUEUE_VISIBILITY_SECONDS, MAX_JOB_ATTEMPTS | Visibility/heartbeat and failure budget |
| STORAGE_PROVIDER | local or s3 |
| LOCAL_STORAGE_PATH, EVIDENCE_BUCKET | Local document root or private S3 bucket |
| SEARCH_PROVIDER | mock or approved_api |
| SEARCH_API_URL, SEARCH_API_KEY | Approved vendor-neutral search endpoint and bearer credential |
| APPROVED_FETCH_DOMAINS | Exact hostname allowlist for HTTPS fetching |
| EMAIL_PROVIDER | mock only in V1 |
| INSTAGRAM_PROVIDER | manual only in V1 |
| REAL_EMAIL_ENABLED, REAL_INSTAGRAM_SEND_ENABLED | Must be false; true is rejected at startup |
| COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID | JWT issuer and access-token client validation |
| SCHEDULER_ROLE_ARN, SCHEDULER_GROUP | Follow-up scheduler target permission and group |
| VITE_API_URL | Browser API origin; bundled public configuration |
| VITE_COGNITO_DOMAIN, VITE_COGNITO_CLIENT_ID | Hosted UI and public OAuth client; no secret |

Never put secret values in a `VITE_*` variable. Terraform creates secret containers, not secret values. The platform refuses local authentication outside local/test and refuses mock AI/search in prod.

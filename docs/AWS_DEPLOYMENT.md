# AWS deployment

No AWS resources were applied during this build. Validate locally first. A reviewed plan and explicit human approval are required before provisioning resources or changing desired service counts.

**Connection update, 21 September 2026:** profile `qima-deploy` now authenticates through company SSO. The assigned `NetworkAdministrator` role is denied access to eight required service-inspection actions. Deployment is waiting for an authorized deployment role and the remaining hosting configuration. See [AWS access request](AWS_ACCESS_REQUEST.md) for the verified account, exact denials and administrator handoff.

## Development first

1. Obtain a development AWS account/profile with SSO or temporary credentials and choose a region.
2. Confirm a Bedrock model or inference profile is enabled in that account and region. Set the exact model/profile identifier, not a guessed model ID.
3. Review the small `infra/environments/dev` plan: discovery queue/DLQ, encrypted private versioned evidence bucket, logs, alarms, Scheduler role/group, development resource policy and secret containers.
4. Following approved provisioning, copy `terraform output -json application` values into local `.env`. Attach the development policy to the approved SSO role, plus a separate policy granting `bedrock:InvokeModel` on the chosen model/profile resources.
5. Set `QUEUE_PROVIDER=sqs`, `STORAGE_PROVIDER=s3`, `AI_PROVIDER=bedrock`. Keep `EMAIL_PROVIDER=mock`, `INSTAGRAM_PROVIDER=manual` and both real-send flags false.
6. Run the same local workflow; confirm SQS processing, visibility extension and versioned S3 objects. Run `scripts/bedrock-smoke.py` manually only when you authorize billable inference.

## Production prerequisites

Production rejects local auth and mock discovery/model settings. Supply an approved search API endpoint/key and a reviewed hostname allowlist. A real model with mock search is a development mode, not production research.

The production module describes private ECS tasks and RDS, public HTTPS ALB, Cognito code/PKCE access, encrypted S3, CloudFront OAC, ECR, Scheduler, logs and alarms. Keep API and worker desired counts at zero until images, secret values, database roles and migrations exist. NAT gateways, RDS, ALB and Fargate create ongoing cost; do not provision them just to inspect the code.

- **DNS/TLS:** supply a regional ACM certificate matching `api_origin_hostname`. Set Route 53 zone ID for managed records, or configure DNS externally. A custom CloudFront hostname needs a certificate in us-east-1. Default CloudFront hostname needs no custom frontend certificate.
- **Database:** RDS generates its admin password through managed Secrets Manager integration. Do not grant application tasks access to the admin secret. An authorized operator must create a scoped application database role and store `{"username":"...","password":"..."}` in the application database secret. Grant schema/table/sequence rights needed for migrations and runtime; organizations requiring separate migration privileges should use a separate migration role/task. RDS requires TLS, and ECS verifies the server certificate using the bundled public RDS CA chain.
- **Integration secret:** populate `{"search_api_key":"..."}` in the integrations secret. Terraform intentionally contains no secret values or secret-version resources.
- **Users:** create approved Cognito users and assign ADMIN, MARKETING, SOURCING, REVIEWER or VIEWER groups. Self-signup is disabled; MFA is required.
- **Artifacts:** push reviewed image tags to ECR and retain immutable tags. Build Vite with the public API origin, Cognito domain and client ID.
- **Migrations:** run one reviewed ECS migration task before service rollout. Failure stops deployment. The supplied workflow runs policy seeding without fictional production data.
- **Alarms:** configure SNS `alarm_actions`; creating an alarm with an empty action list does not notify an operator.

## CI/CD and OIDC

PR checks run lint, type checks, unit tests, E2E integration, image builds, dependency audits and Terraform validation. Deployment is manually dispatched from main and depends on those checks. Configure GitHub protected environments with required reviewers; branch protection and environment protection cannot be installed by files alone.

Use the trust-policy example under `infra/bootstrap` with the exact repository and environment subject, not a wildcard. The deployment role needs only its ECR repositories; scoped ECS services/task families; PassRole for the task/execution roles; frontend bucket writes; CloudFront invalidation; and read/wait operations. ECR GetAuthorizationToken necessarily uses Resource `*`. No permanent AWS keys are used. Creating this role/provider is an account-administration prerequisite.

GitHub environment variables are enumerated by `deploy.yml`: region/deploy-role, ECR repositories, ECS cluster/services/task families/private subnet CSV/security group, API URL, Cognito domain/client, frontend bucket and distribution ID. Production policy protection must reject unreviewed branches.

## Sources checked

- [Boto3 Converse API](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html): supported message/inference/output interface.
- [Cognito access-token claims](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html): issuer, client_id, token_use and group semantics.
- [Terraform AWS ECS service reference](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service): production service configuration; installed AWS provider schema validation is the build's local verification.

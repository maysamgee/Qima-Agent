# AWS deployment access request template

## Example connection - historical limited-role checks

Replace the placeholders below with your deployment account details. Account-specific results and private copies belong in the Git-ignored `.local/` directory. The restrictions in this example describe historical checks with a limited network role, not the current permissions of any account.

Authenticate the AWS CLI through IAM Identity Center using profile `qima-deploy`.

- Account: `<AWS_ACCOUNT_ID>`
- SSO portal: `<AWS_ACCESS_PORTAL_URL>`
- SSO region: `us-east-1`
- Available permission set: `NetworkAdministrator`
- Signed-in user: `<DEPLOYMENT_USER>`
- STS identity: `arn:aws:sts::<AWS_ACCOUNT_ID>:assumed-role/<SSO_ROLE_NAME>/<DEPLOYMENT_USER>`

`us-east-1` was used for these read-only checks. The hosting region still needs confirmation. No Terraform apply, model invocation, application deployment, IAM permission change or application-resource creation was performed.

## Observed access restrictions

The historical example returned explicit access-denied responses because no identity-based policy allows these actions:

| Component | Denied action |
| --- | --- |
| ECS API and worker hosting | `ecs:ListClusters` |
| PostgreSQL database | `rds:DescribeDBInstances` |
| Container image repositories | `ecr:DescribeRepositories` |
| User authentication | `cognito-idp:ListUserPools` |
| Object storage | `s3:ListAllMyBuckets` |
| HTTPS certificates | `acm:ListCertificates` |
| AI model discovery | `bedrock:ListFoundationModels` |
| IAM deployment roles | `iam:ListRoles` |

VPC inspection, Route 53 hosted-zone listing and CloudFront distribution listing succeeded. CloudShell reported that it could not create an environment; that screen did not establish a more specific cause.

These are read-only checks, not a complete policy simulation. Passing a read check does not prove write permission; broad listing rights can also be withheld from otherwise scoped roles. The application's Terraform and deployment workflow require additional resource-management permissions, so adding only the eight read actions above is insufficient.

The machine-local detailed results are retained in `.local/aws-preflight.json`, which is ignored by Git and contains no secret values.

## Request for the AWS administrator

Please assign <DEPLOYMENT_USER> a deployment-capable IAM Identity Center permission set for the standalone **Qima Discovery & Outreach Agent Platform** in account `<AWS_ACCOUNT_ID>`. A dedicated permission set such as `QimaAgentsDeployment` is preferable to changing the existing network role or granting unrestricted administrator access.

Review the exact Terraform resources under `infra/bootstrap`, `infra/environments/prod` and `infra/modules`, plus `.github/workflows/deploy.yml`, when defining permissions. The required scope is:

- Manage project VPC/subnets/routes/NAT, security groups and ALB resources, using the `qima-agents-*` names and project tags where service authorization supports them.
- Manage the project's ECS cluster/services/task definitions and ECR repositories; upload reviewed container images and run the migration task.
- Manage the project's private RDS PostgreSQL instance, subnet/parameter groups and managed database secret; enable the specified backups and encryption.
- Manage the project's private/versioned S3 buckets, CloudFront distribution and frontend artifacts. Allow an explicitly selected Terraform state bucket/key and its lock file.
- Manage project SQS queues/DLQs, Scheduler group/schedules, CloudWatch log groups/alarms and Cognito pool/client/groups.
- Create and manage only project IAM roles/policies, with `iam:PassRole` restricted to the required ECS task/execution and Scheduler roles and their intended AWS services. Permit required AWS service-linked roles only as applicable.
- Manage project Secrets Manager containers/values through an approved process. Secret values must not be put in Terraform variables or state.
- List applicable Bedrock models/profiles and invoke only the selected, approved model/profile resources.
- Inspect and use the approved ACM certificates and DNS zone, with DNS changes limited to the application's agreed hostnames.

Apply resource ARN and tag restrictions where supported; actions that require `Resource: "*"` need individual review. Any organization SCPs, permission boundaries, SSO session policies and regional restrictions must also permit the deployment. The existing Qima applications and repositories are outside this request.

No permissions have been changed by the assistant, and this request has not been sent to anyone.

## Resume after access is assigned

Tell the assistant the new permission-set name. If the profile selects a limited role such as `NetworkAdministrator`, update it to the newly assigned role before signing in again. Alternatively, rerun the wizard and select the authorized deployment role:

```powershell
$aws = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
& $aws configure sso --profile qima-deploy
& $aws sts get-caller-identity --profile qima-deploy
.\.venv\Scripts\python.exe scripts/aws-preflight.py --profile qima-deploy --region us-east-1 --expected-account "<AWS_ACCOUNT_ID>"
```

Then confirm the hosting region, API domain/TLS certificate, approved search provider and enabled Bedrock model. Prepare and review the actual Terraform plan before provisioning, following the original requirement for explicit approval before `terraform apply` or expensive AWS resources. Keep real email and Instagram sending disabled.

Reference: [AWS CLI IAM Identity Center configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

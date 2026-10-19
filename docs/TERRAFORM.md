# Terraform operations

Terraform 1.12.2 and AWS provider 6.65.0 were used for local validation. Each environment has a committed provider lock file. No account IDs are hard-coded in infrastructure. Default tags are Project, Environment, Owner, ManagedBy=Terraform and optional CostCenter.

## Offline configuration validation

Run from the repository root:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false -input=false
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/environments/dev init -backend=false -input=false
terraform -chdir=infra/environments/dev validate
terraform -chdir=infra/environments/prod init -backend=false -input=false
terraform -chdir=infra/environments/prod validate
```

Provider installation needs internet access but no AWS credentials. Validation checks resource schemas and expressions, not account permissions, quotas, pricing or service availability.

## Remote state bootstrap

The bootstrap configuration describes a private, encrypted, versioned S3 state bucket with `prevent_destroy`. A human must approve its initial plan/apply or supply an existing approved state bucket. The bootstrap initially uses local state; protect it and migrate it to the organization's managed backend after approved creation.

Use separate state keys for dev and prod. S3 lockfile support is enabled in `backend.hcl.example`. The state role needs GetObject/PutObject on the state key and GetObject/PutObject/DeleteObject on its `.tflock` key. It should not have broad bucket deletion rights.

## Review a development plan

```powershell
$env:AWS_PROFILE = 'qima-dev'
Set-Location infra\environments\dev
Copy-Item terraform.tfvars.example terraform.tfvars
Copy-Item backend.hcl.example backend.hcl
# Edit non-secret account/region/owner and state-bucket settings.
terraform init -reconfigure -backend-config=backend.hcl
terraform plan -out=dev.tfplan
terraform show dev.tfplan
```

**Stop for explicit human approval before any `terraform apply`.** Do not commit `.tfvars`, plans, state or backend account configuration. Plan files may contain sensitive values even when their console display is redacted. Secret values must be inserted directly into Secrets Manager after approval, not through Terraform.

Production uses the same steps in `infra/environments/prod` after reviewing sizing, NAT strategy (single/per_az), RDS Multi-AZ, certificates, DNS, model/profile resources, approved search, service counts and alarm destinations. The state bootstrap and dev configuration do not provision ECS, RDS, ALB or CloudFront.

Deletion protection, retained S3 objects and final RDS snapshots intentionally make teardown nontrivial. No automatic destroy procedure is included.

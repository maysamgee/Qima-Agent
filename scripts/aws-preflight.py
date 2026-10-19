"""Read-only account and service-access checks before planning a deployment.

This does not create resources, invoke models, retrieve secret values or test write
permissions. Passing it is not proof that every deployment action is authorized.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--output", default=".local/aws-preflight.json")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    config = Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 1})
    identity = session.client("sts", config=config).get_caller_identity()
    if identity["Account"] != args.expected_account:
        raise SystemExit("Connected AWS account differs from the expected account; checks stopped.")

    # Create clients before starting threads; botocore clients support these read calls concurrently.
    operations = [
        ("EC2 networking", "ec2", "describe_vpcs", {"MaxResults": 5}, "Vpcs"),
        ("ECS services", "ecs", "list_clusters", {"maxResults": 10}, "clusterArns"),
        ("RDS databases", "rds", "describe_db_instances", {"MaxRecords": 20}, "DBInstances"),
        ("ECR images", "ecr", "describe_repositories", {"maxResults": 20}, "repositories"),
        ("Cognito users", "cognito-idp", "list_user_pools", {"MaxResults": 10}, "UserPools"),
        ("S3 storage", "s3", "list_buckets", {}, "Buckets"),
        ("ACM certificates", "acm", "list_certificates", {"MaxItems": 10}, "CertificateSummaryList"),
        ("Route 53 domains", "route53", "list_hosted_zones", {"MaxItems": "10"}, "HostedZones"),
        (
            "Bedrock models",
            "bedrock",
            "list_foundation_models",
            {"byOutputModality": "TEXT"},
            "modelSummaries",
        ),
        ("CloudFront hosting", "cloudfront", "list_distributions", {"MaxItems": "10"}, "DistributionList"),
        ("IAM role inspection", "iam", "list_roles", {"MaxItems": 10}, "Roles"),
    ]
    clients = {service: session.client(service, config=config) for _, service, _, _, _ in operations}

    def check(operation):
        name, service, method, parameters, result_key = operation
        result = {"service": name, "operation": f"{service}.{method}"}
        try:
            response = getattr(clients[service], method)(**parameters)
            records = response.get(result_key, [])
            count = records.get("Quantity", 0) if isinstance(records, dict) else len(records)
            return {**result, "status": "PASS", "returned_count": count}
        except ClientError as error:
            failure = error.response["Error"]
            return {**result, "status": "BLOCKED", "code": failure["Code"], "message": failure["Message"]}
        except BotoCoreError as error:
            return {**result, "status": "ERROR", "code": type(error).__name__}

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(check, operations))
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "region": args.region,
        "account": identity["Account"],
        "principal": identity["Arn"],
        "read_only": True,
        "write_permissions_verified": False,
        "checks": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(any(result["status"] != "PASS" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())

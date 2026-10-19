"""Read-only, paginated AWS inventory; stores identifiers/metadata, never secret values."""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import boto3
import jmespath
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

# Type, service, read operation, result expression, identifier expression, parameters.
REGIONAL = [
    ("EC2 instances", "ec2", "describe_instances", "Reservations[].Instances[]", "InstanceId", {}),
    ("EBS volumes", "ec2", "describe_volumes", "Volumes", "VolumeId", {}),
    ("EBS owned snapshots", "ec2", "describe_snapshots", "Snapshots", "SnapshotId", {"OwnerIds": ["self"]}),
    ("Owned AMIs", "ec2", "describe_images", "Images", "ImageId", {"Owners": ["self"]}),
    ("VPCs", "ec2", "describe_vpcs", "Vpcs", "VpcId", {}),
    ("Subnets", "ec2", "describe_subnets", "Subnets", "SubnetId", {}),
    ("Route tables", "ec2", "describe_route_tables", "RouteTables", "RouteTableId", {}),
    ("Security groups", "ec2", "describe_security_groups", "SecurityGroups", "GroupId", {}),
    ("Network ACLs", "ec2", "describe_network_acls", "NetworkAcls", "NetworkAclId", {}),
    ("Internet gateways", "ec2", "describe_internet_gateways", "InternetGateways", "InternetGatewayId", {}),
    ("NAT gateways", "ec2", "describe_nat_gateways", "NatGateways", "NatGatewayId", {}),
    ("Elastic IP allocations", "ec2", "describe_addresses", "Addresses", "AllocationId || PublicIp", {}),
    (
        "Network interfaces",
        "ec2",
        "describe_network_interfaces",
        "NetworkInterfaces",
        "NetworkInterfaceId",
        {},
    ),
    ("VPC endpoints", "ec2", "describe_vpc_endpoints", "VpcEndpoints", "VpcEndpointId", {}),
    (
        "VPC peering connections",
        "ec2",
        "describe_vpc_peering_connections",
        "VpcPeeringConnections",
        "VpcPeeringConnectionId",
        {},
    ),
    ("Transit gateways", "ec2", "describe_transit_gateways", "TransitGateways", "TransitGatewayId", {}),
    ("VPN connections", "ec2", "describe_vpn_connections", "VpnConnections", "VpnConnectionId", {}),
    ("VPN gateways", "ec2", "describe_vpn_gateways", "VpnGateways", "VpnGatewayId", {}),
    ("Customer gateways", "ec2", "describe_customer_gateways", "CustomerGateways", "CustomerGatewayId", {}),
    ("EC2 launch templates", "ec2", "describe_launch_templates", "LaunchTemplates", "LaunchTemplateId", {}),
    (
        "Auto Scaling groups",
        "autoscaling",
        "describe_auto_scaling_groups",
        "AutoScalingGroups",
        "AutoScalingGroupARN",
        {},
    ),
    (
        "Load balancers (ALB/NLB/GWLB)",
        "elbv2",
        "describe_load_balancers",
        "LoadBalancers",
        "LoadBalancerArn",
        {},
    ),
    (
        "Classic load balancers",
        "elb",
        "describe_load_balancers",
        "LoadBalancerDescriptions",
        "LoadBalancerName",
        {},
    ),
    ("Lambda functions", "lambda", "list_functions", "Functions", "FunctionArn", {}),
    ("ECS clusters", "ecs", "list_clusters", "clusterArns", "@", {}),
    ("EKS clusters", "eks", "list_clusters", "clusters", "@", {}),
    ("ECR repositories", "ecr", "describe_repositories", "repositories", "repositoryArn", {}),
    ("RDS DB instances", "rds", "describe_db_instances", "DBInstances", "DBInstanceArn", {}),
    ("RDS DB clusters", "rds", "describe_db_clusters", "DBClusters", "DBClusterArn", {}),
    ("RDS DB proxies", "rds", "describe_db_proxies", "DBProxies", "DBProxyArn", {}),
    ("DynamoDB tables", "dynamodb", "list_tables", "TableNames", "@", {}),
    (
        "ElastiCache clusters",
        "elasticache",
        "describe_cache_clusters",
        "CacheClusters",
        "ARN || CacheClusterId",
        {},
    ),
    (
        "ElastiCache serverless caches",
        "elasticache",
        "describe_serverless_caches",
        "ServerlessCaches",
        "ARN",
        {},
    ),
    ("Redshift clusters", "redshift", "describe_clusters", "Clusters", "ClusterIdentifier", {}),
    ("OpenSearch domains", "opensearch", "list_domain_names", "DomainNames", "DomainName", {}),
    ("EFS file systems", "efs", "describe_file_systems", "FileSystems", "FileSystemId", {}),
    ("FSx file systems", "fsx", "describe_file_systems", "FileSystems", "FileSystemId", {}),
    ("Backup vaults", "backup", "list_backup_vaults", "BackupVaultList", "BackupVaultArn", {}),
    ("SQS queues", "sqs", "list_queues", "QueueUrls", "@", {"MaxResults": 1000}),
    ("SNS topics", "sns", "list_topics", "Topics", "TopicArn", {}),
    ("EventBridge buses", "events", "list_event_buses", "EventBuses", "Arn", {}),
    ("Scheduler schedules", "scheduler", "list_schedules", "Schedules", "Arn", {}),
    (
        "Step Functions state machines",
        "stepfunctions",
        "list_state_machines",
        "stateMachines",
        "stateMachineArn",
        {},
    ),
    ("API Gateway REST APIs", "apigateway", "get_rest_apis", "items", "id", {}),
    ("API Gateway HTTP/WebSocket APIs", "apigatewayv2", "get_apis", "Items", "ApiId", {}),
    ("AppSync APIs", "appsync", "list_graphql_apis", "graphqlApis", "arn", {}),
    ("Cognito user pools", "cognito-idp", "list_user_pools", "UserPools", "Id", {"MaxResults": 60}),
    (
        "Cognito identity pools",
        "cognito-identity",
        "list_identity_pools",
        "IdentityPools",
        "IdentityPoolId",
        {"MaxResults": 60},
    ),
    ("Secrets Manager secrets (metadata)", "secretsmanager", "list_secrets", "SecretList", "ARN", {}),
    ("KMS keys", "kms", "list_keys", "Keys", "KeyArn", {}),
    ("ACM certificates", "acm", "list_certificates", "CertificateSummaryList", "CertificateArn", {}),
    ("CloudWatch log groups", "logs", "describe_log_groups", "logGroups", "arn || logGroupName", {}),
    (
        "CloudWatch alarms",
        "cloudwatch",
        "describe_alarms",
        "[MetricAlarms, CompositeAlarms][]",
        "AlarmArn",
        {"AlarmTypes": ["MetricAlarm", "CompositeAlarm"]},
    ),
    ("CloudFormation stacks", "cloudformation", "describe_stacks", "Stacks", "StackId", {}),
    (
        "CloudTrail trails",
        "cloudtrail",
        "describe_trails",
        "trailList",
        "TrailARN",
        {"includeShadowTrails": False},
    ),
    ("CodeBuild projects", "codebuild", "list_projects", "projects", "@", {}),
    ("CodePipeline pipelines", "codepipeline", "list_pipelines", "pipelines", "name", {}),
    (
        "Elastic Beanstalk environments",
        "elasticbeanstalk",
        "describe_environments",
        "Environments",
        "EnvironmentArn",
        {"IncludeDeleted": False},
    ),
    ("App Runner services", "apprunner", "list_services", "ServiceSummaryList", "ServiceArn", {}),
    ("Amplify apps", "amplify", "list_apps", "apps", "appArn", {}),
    ("SageMaker endpoints", "sagemaker", "list_endpoints", "Endpoints", "EndpointArn", {}),
    (
        "SageMaker notebook instances",
        "sagemaker",
        "list_notebook_instances",
        "NotebookInstances",
        "NotebookInstanceArn",
        {},
    ),
    ("Bedrock custom models", "bedrock", "list_custom_models", "modelSummaries", "modelArn", {}),
    (
        "Bedrock provisioned throughput",
        "bedrock",
        "list_provisioned_model_throughputs",
        "provisionedModelSummaries",
        "provisionedModelArn",
        {},
    ),
    ("Bedrock agents", "bedrock-agent", "list_agents", "agentSummaries", "agentId", {}),
    (
        "Bedrock knowledge bases",
        "bedrock-agent",
        "list_knowledge_bases",
        "knowledgeBaseSummaries",
        "knowledgeBaseId",
        {},
    ),
    ("Kinesis streams", "kinesis", "list_streams", "StreamNames", "@", {}),
    ("Firehose delivery streams", "firehose", "list_delivery_streams", "DeliveryStreamNames", "@", {}),
    ("Amazon MQ brokers", "mq", "list_brokers", "BrokerSummaries", "BrokerArn", {}),
    ("MSK clusters", "kafka", "list_clusters_v2", "ClusterInfoList", "ClusterArn", {}),
    ("Lightsail instances", "lightsail", "get_instances", "instances", "arn", {}),
    ("Lightsail databases", "lightsail", "get_relational_databases", "relationalDatabases", "arn", {}),
    ("WAF regional web ACLs", "wafv2", "list_web_acls", "WebACLs", "ARN", {"Scope": "REGIONAL"}),
    ("Resource Explorer views", "resource-explorer-2", "list_views", "Views", "@", {}),
]
GLOBAL = [
    ("S3 buckets", "s3", "list_buckets", "Buckets", "Name", {"MaxBuckets": 1000}),
    ("Resource Explorer indexes", "resource-explorer-2", "list_indexes", "Indexes", "Arn", {}),
    ("CloudFront distributions", "cloudfront", "list_distributions", "DistributionList.Items", "ARN", {}),
    ("Route 53 hosted zones", "route53", "list_hosted_zones", "HostedZones", "Id", {}),
    ("Route 53 registered domains", "route53domains", "list_domains", "Domains", "DomainName", {}),
    ("Route 53 health checks", "route53", "list_health_checks", "HealthChecks", "Id", {}),
    ("IAM users", "iam", "list_users", "Users", "Arn", {}),
    ("IAM roles", "iam", "list_roles", "Roles", "Arn", {}),
    ("IAM customer-managed policies", "iam", "list_policies", "Policies", "Arn", {"Scope": "Local"}),
    ("WAF CloudFront web ACLs", "wafv2", "list_web_acls", "WebACLs", "ARN", {"Scope": "CLOUDFRONT"}),
]
CONFIG = Config(connect_timeout=6, read_timeout=12, retries={"max_attempts": 1, "mode": "standard"})
SAFE_FIELDS = (
    "InstanceType",
    "VpcId",
    "SubnetId",
    "CidrBlock",
    "IsDefault",
    "DefaultForAz",
    "IsMain",
    "GroupName",
    "Size",
    "VolumeType",
    "DBInstanceClass",
    "Engine",
    "EngineVersion",
    "DBInstanceStatus",
    "Status",
    "Type",
    "Enabled",
    "Runtime",
    "MemorySize",
    "Timeout",
    "DomainName",
    "BucketRegion",
    "CreationDate",
    "Region",
    "StorageBytes",
    "storedBytes",
    "retentionInDays",
    "DesiredCapacity",
    "MinSize",
    "MaxSize",
    "DBClusterIdentifier",
    "PubliclyAccessible",
    "MultiAZ",
    "HomeRegion",
    "StackStatus",
    "state",
)


def collect_region(profile, region, specs):
    session = boto3.Session(profile_name=profile, region_name="us-east-1" if region == "global" else region)
    clients = {}
    results = []
    resources = []

    def run(spec):
        label, service, method, expression, identifier, parameters = spec
        check = {"region": region, "type": label, "operation": f"{service}.{method}"}
        found = []
        try:
            available_regions = session.get_available_regions(service)
            if region != "global" and available_regions and region not in available_regions:
                check.update(status="UNAVAILABLE", count=None, reason="No regional endpoint in installed SDK")
                results.append(check)
                return found
            if service not in clients:
                clients[service] = session.client(service, config=CONFIG)
            client = clients[service]
            if not method.startswith(("list_", "describe_", "get_")):
                raise ValueError("Only inventory reads are permitted")
            if client.can_paginate(method):
                pages = client.get_paginator(method).paginate(**parameters)
            else:
                pages = [getattr(client, method)(**parameters)]
            seen = set()
            truncated = False
            for page in pages:
                if not client.can_paginate(method) and any(
                    page.get(key)
                    for key in (
                        "NextToken",
                        "nextToken",
                        "NextMarker",
                        "nextMarker",
                        "HasMoreStreams",
                        "HasMoreDeliveryStreams",
                    )
                ):
                    truncated = True
                for item in jmespath.search(expression, page) or []:
                    resource_id = jmespath.search(identifier, item)
                    if not resource_id or resource_id in seen:
                        continue
                    record = {"region": region, "type": label, "id": resource_id}
                    if isinstance(item, dict):
                        if label == "S3 buckets" and item.get("BucketRegion"):
                            record["region"] = item["BucketRegion"]
                        elif label == "Resource Explorer indexes" and item.get("Region"):
                            record["region"] = item["Region"]
                        status = item.get("State")
                        if isinstance(status, dict):
                            status = status.get("Name") or status.get("Code")
                        if not status:
                            status = item.get("Status") or item.get("DBInstanceStatus") or item.get("state")
                        if label == "VPC peering connections":
                            status = (item.get("Status") or {}).get("Code")
                        if isinstance(status, str) and status.lower() in {
                            "deleted",
                            "terminated",
                            "delete_complete",
                        }:
                            continue
                        if label == "CloudTrail trails" and item.get("HomeRegion") != region:
                            continue
                        name = next(
                            (
                                item[key]
                                for key in (
                                    "Name",
                                    "name",
                                    "FunctionName",
                                    "DBInstanceIdentifier",
                                    "DBClusterIdentifier",
                                    "DBProxyName",
                                    "ClusterIdentifier",
                                    "StackName",
                                    "LoadBalancerName",
                                    "repositoryName",
                                    "logGroupName",
                                    "appName",
                                    "agentName",
                                    "agentAliasName",
                                )
                                if item.get(key)
                            ),
                            None,
                        )
                        if not name:
                            tags = item.get("Tags", [])
                            if isinstance(tags, list):
                                name = next(
                                    (tag.get("Value") for tag in tags if tag.get("Key") == "Name"), None
                                )
                        if name:
                            record["name"] = name
                        if status:
                            record["status"] = status
                        record["details"] = {key: item[key] for key in SAFE_FIELDS if key in item}
                        if label == "Route tables":
                            record["details"]["main_route_table"] = any(
                                a.get("Main") for a in item.get("Associations", [])
                            )
                        if label == "Internet gateways":
                            record["details"]["vpc_ids"] = [a["VpcId"] for a in item.get("Attachments", [])]
                        if label == "CloudFront distributions":
                            record["details"]["aliases"] = item.get("Aliases", {}).get("Items", [])
                    seen.add(resource_id)
                    resources.append(record)
                    found.append(record)
            check.update(status="PARTIAL" if truncated else "OK", count=len(found))
            if truncated:
                check["reason"] = "SDK has no paginator; response indicated additional results"
        except ClientError as error:
            code = error.response["Error"]["Code"]
            check.update(
                status="DENIED"
                if any(text in code.lower() for text in ("denied", "unauthorized", "forbidden"))
                else "ERROR",
                code=code,
                count=None,
                message=error.response["Error"]["Message"],
            )
        except (BotoCoreError, ValueError, AttributeError) as error:
            check.update(status="ERROR", code=type(error).__name__, count=None, message=str(error)[:400])
        results.append(check)
        return found

    for spec in specs:
        found = run(spec)
        if spec[0] == "ECS clusters":
            for cluster in found:
                for label, method, key in [
                    ("ECS services", "list_services", "serviceArns"),
                    ("ECS running tasks", "list_tasks", "taskArns"),
                ]:
                    run((label, "ecs", method, key, "@", {"cluster": cluster["id"]}))
        elif spec[0] == "EventBridge buses":
            for bus in found:
                run(
                    ("EventBridge rules", "events", "list_rules", "Rules", "Arn", {"EventBusName": bus["id"]})
                )
    return results, resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    session = boto3.Session(profile_name=args.profile, region_name="us-east-1")
    identity = session.client("sts", config=CONFIG).get_caller_identity()
    if identity["Account"] != args.expected_account:
        raise SystemExit("Unexpected AWS account; inventory stopped")
    regions = session.client("ec2", config=CONFIG).describe_regions(AllRegions=True)["Regions"]
    enabled = sorted(
        r["RegionName"] for r in regions if r["OptInStatus"] in {"opt-in-not-required", "opted-in"}
    )
    report = {
        "started_at": started,
        "account": identity["Account"],
        "principal": identity["Arn"],
        "profile": args.profile,
        "enabled_regions": enabled,
        "disabled_regions": sorted(r["RegionName"] for r in regions if r["OptInStatus"] == "not-opted-in"),
        "read_only": True,
        "scope": "Direct service API inventory of the enumerated resource types, with SDK pagination. Not an exhaustive inventory of every AWS service. Disabled regions are not scanned. Secret values, object contents and application data are never retrieved. Stack/cluster containers and child resources are separate AWS objects; totals are not workload counts.",
        "checks": [],
        "resources": [],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {
            pool.submit(collect_region, args.profile, r, GLOBAL if r == "global" else REGIONAL): r
            for r in ["global", *enabled]
        }
        for task in as_completed(tasks):
            region = tasks[task]
            try:
                checks, resources = task.result()
            except Exception as error:  # noqa: BLE001 - Preserve other regions when one scan fails.
                checks, resources = (
                    [
                        {
                            "region": region,
                            "type": "REGION_SCAN",
                            "status": "ERROR",
                            "code": type(error).__name__,
                            "message": str(error)[:400],
                        }
                    ],
                    [],
                )
            report["checks"].extend(checks)
            report["resources"].extend(resources)
            output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "region": region,
                        "objects": len(resources),
                        "checks": dict(Counter(c["status"] for c in checks)),
                    }
                ),
                flush=True,
            )
    unique = {(r["region"], r["type"], r["id"]): r for r in report["resources"]}
    report["resources"] = sorted(unique.values(), key=lambda r: (r["region"], r["type"], r["id"]))
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["observed_object_count"] = len(unique)
    report["counts_by_type"] = dict(sorted(Counter(r["type"] for r in unique.values()).items()))
    report["counts_by_region"] = dict(sorted(Counter(r["region"] for r in unique.values()).items()))
    report["coverage"] = dict(Counter(c["status"] for c in report["checks"]))
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "account",
                    "observed_object_count",
                    "counts_by_type",
                    "counts_by_region",
                    "coverage",
                )
            },
            indent=2,
        ),
        flush=True,
    )
    print(f"Inventory saved to {output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Invoked only by the reviewed, protected deployment workflow. Never runs Terraform apply.
set -euo pipefail
required=(ECS_CLUSTER API_SERVICE WORKER_SERVICE API_TASK_FAMILY WORKER_TASK_FAMILY API_REPOSITORY WORKER_REPOSITORY ECS_PRIVATE_SUBNETS ECS_SECURITY_GROUP RELEASE_SHA)
for key in "${required[@]}"; do test -n "${!key:-}" || { echo "Missing configuration: $key"; exit 1; }; done
register_task() {
  local family="$1" image="$2" container="$3" target="$4"
  aws ecs describe-task-definition --task-definition "$family" --query taskDefinition > "$target.source.json"
  jq --arg image "$image" --arg name "$container" 'del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy) | (.containerDefinitions[] | select(.name==$name) | .image)=$image' "$target.source.json" > "$target.json"
  aws ecs register-task-definition --cli-input-json "file://$target.json" --query taskDefinition.taskDefinitionArn --output text
}
api_task=$(register_task "$API_TASK_FAMILY" "$API_REPOSITORY:$RELEASE_SHA" api api-release)
worker_task=$(register_task "$WORKER_TASK_FAMILY" "$WORKER_REPOSITORY:$RELEASE_SHA" worker worker-release)
jq -n --arg subnets "$ECS_PRIVATE_SUBNETS" --arg sg "$ECS_SECURITY_GROUP" '{awsvpcConfiguration:{subnets:($subnets|split(",")),securityGroups:[$sg],assignPublicIp:"DISABLED"}}' > migration-network.json
printf '%s\n' '{"containerOverrides":[{"name":"api","command":["sh","-c","python -m alembic upgrade head && python -m app.seed"]}]}' > migration-overrides.json
migration=$(aws ecs run-task --cluster "$ECS_CLUSTER" --launch-type FARGATE --task-definition "$api_task" --network-configuration file://migration-network.json --overrides file://migration-overrides.json --query 'tasks[0].taskArn' --output text)
test "$migration" != None || { echo 'Migration task did not start'; exit 1; }
aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$migration"
exit_code=$(aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks "$migration" --query 'tasks[0].containers[0].exitCode' --output text)
test "$exit_code" = 0 || { echo 'Migration failed; services were not updated'; exit 1; }
aws ecs update-service --cluster "$ECS_CLUSTER" --service "$API_SERVICE" --task-definition "$api_task" > /dev/null
aws ecs update-service --cluster "$ECS_CLUSTER" --service "$WORKER_SERVICE" --task-definition "$worker_task" > /dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$API_SERVICE" "$WORKER_SERVICE"

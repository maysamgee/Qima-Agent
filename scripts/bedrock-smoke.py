"""Manual, billable smoke test: run only after configuring AI_PROVIDER=bedrock."""
from app.ai.model import BedrockModelService
from app.config import get_settings

if __name__ == "__main__":
    if get_settings().ai_provider != "bedrock":
        raise SystemExit("Set AI_PROVIDER=bedrock, AWS_REGION and BEDROCK_MODEL_ID or inference profile first.")
    service = BedrockModelService()
    result = service.classify_reply("This is a fictional smoke test. We would like more information.")
    print(result.model_dump_json(indent=2))
    print(service.last_usage)

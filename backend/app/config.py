from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    app_env: Literal["local", "test", "dev", "prod"] = "local"
    auth_mode: Literal["local", "cognito"] = "local"
    database_url: str = "postgresql+psycopg://qima:qima@localhost:5432/qima_agents"
    cors_origins: str = "http://localhost:5173"
    aws_profile: str = ""
    aws_region: str = ""
    ai_provider: Literal["mock", "bedrock"] = "mock"
    bedrock_model_id: str = ""
    bedrock_inference_profile_arn: str = ""
    bedrock_temperature: float = 0.2
    bedrock_max_output_tokens: int = 2048
    bedrock_max_tool_iterations: int = 8
    bedrock_request_timeout_seconds: int = 120
    tool_timeout_seconds: int = 20
    job_timeout_seconds: int = 600
    queue_provider: Literal["local", "sqs"] = "local"
    discovery_queue_url: str = ""
    discovery_dlq_url: str = ""
    queue_visibility_seconds: int = 120
    max_job_attempts: int = 5
    storage_provider: Literal["local", "s3"] = "local"
    local_storage_path: str = ".local/documents"
    evidence_bucket: str = ""
    search_provider: Literal["mock", "approved_api"] = "mock"
    search_api_url: str = ""
    search_api_key: str = ""
    approved_fetch_domains: str = ""
    instagram_provider: Literal["manual"] = "manual"
    email_provider: Literal["mock"] = "mock"
    real_email_enabled: bool = False
    real_instagram_send_enabled: bool = False
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    scheduler_role_arn: str = ""
    scheduler_group: str = "default"
    database_secret_arn: str = ""
    database_host: str = ""
    database_name: str = "qima_agents"
    database_sslmode: Literal["prefer", "require", "verify-full"] = "prefer"
    database_sslrootcert: str = ""

    @model_validator(mode="after")
    def safe_configuration(self):
        if self.real_email_enabled or self.real_instagram_send_enabled:
            raise ValueError("V1 supports simulated email and manual Instagram only")
        if self.app_env not in {"local", "test"} and self.auth_mode == "local":
            raise ValueError("Local authentication is restricted to local/test")
        if self.auth_mode == "cognito" and not all(
            [self.aws_region, self.cognito_user_pool_id, self.cognito_app_client_id]
        ):
            raise ValueError("Cognito region, user pool and app client are required")
        if self.ai_provider == "bedrock" and not (
            self.aws_region and (self.bedrock_model_id or self.bedrock_inference_profile_arn)
        ):
            raise ValueError("Bedrock requires region and a model or inference profile")
        if self.app_env == "prod" and (self.ai_provider == "mock" or self.search_provider == "mock"):
            raise ValueError("Production requires configured AI and discovery providers")
        if self.queue_provider == "sqs" and not self.discovery_queue_url:
            raise ValueError("SQS queue URL is required")
        if self.storage_provider == "s3" and not self.evidence_bucket:
            raise ValueError("S3 evidence bucket is required")
        if self.search_provider == "approved_api" and not self.search_api_url.startswith("https://"):
            raise ValueError("Approved search API must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

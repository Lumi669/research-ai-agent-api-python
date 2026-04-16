from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    node_env: str = Field(default="development", alias="NODE_ENV")
    port: int = Field(default=8000, alias="PORT")
    internal_api_key: str | None = Field(default=None, alias="INTERNAL_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_MODEL")
    aws_region: str = Field(default="eu-north-1", alias="AWS_REGION")
    dynamodb_table_name: str | None = Field(default=None, alias="DYNAMODB_TABLE_NAME")
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    s3_bucket_name: str | None = Field(default=None, alias="S3_BUCKET_NAME")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_upload_prefix: str = Field(default="conversations", alias="S3_UPLOAD_PREFIX")
    s3_presign_ttl_seconds: int = Field(default=900, alias="S3_PRESIGN_TTL_SECONDS")
    mock_openai: bool = Field(default=False, alias="MOCK_OPENAI")
    agent_provider: str = Field(default="openai", alias="AGENT_PROVIDER")
    usage_store_path: str = Field(default=".data/usage_events.json", alias="USAGE_STORE_PATH")


settings = Settings()

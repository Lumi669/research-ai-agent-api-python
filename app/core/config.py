from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    node_env: str = Field(default="development", alias="NODE_ENV")
    port: int = Field(default=8000, alias="PORT")
    internal_api_key: str | None = Field(default=None, alias="INTERNAL_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_MODEL")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    dynamodb_table_name: str | None = Field(default=None, alias="DYNAMODB_TABLE_NAME")
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    mock_openai: bool = Field(default=False, alias="MOCK_OPENAI")
    agent_provider: str = Field(default="openai", alias="AGENT_PROVIDER")


settings = Settings()

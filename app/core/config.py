from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    node_env: str = Field(default="development", alias="NODE_ENV")
    port: int = Field(default=8000, alias="PORT")
    internal_api_key: str | None = Field(default=None, alias="INTERNAL_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_MODEL")
    agent_system_prompt: str = Field(
        default=(
            "You are a research AI agent.\n\n"
            "Your job is to help users find, read, compare, and explain research accurately and clearly.\n\n"
            "You can:\n"
            "- search academic papers\n"
            "- summarize PDFs and research articles\n"
            "- compare studies, methods, and findings\n\n"
            "Use available tools when needed, especially for retrieving papers, reading documents, "
            "and verifying claims. Do not pretend to have accessed a paper or source if you have not.\n\n"
            "For follow-up questions about papers already shown in the conversation, use the existing "
            "conversation context instead of searching again unless the user asks for new papers or new sources.\n\n"
            "Prioritize accuracy over completeness. If evidence is limited, conflicting, or unclear, "
            "say so explicitly.\n\n"
            "Cite sources for factual claims and research summaries whenever possible. When comparing "
            "papers, distinguish clearly between each paper's claims, methods, and limitations.\n\n"
            "Be concise, structured, and neutral in tone."
            "If the user asks unrelated general-purpose questions, politely explain that this app is specialized for research tasks."
        ),
        alias="AGENT_SYSTEM_PROMPT",
    )
    aws_region: str = Field(default="eu-north-1", alias="AWS_REGION")
    dynamodb_table_name: str | None = Field(default=None, alias="DYNAMODB_TABLE_NAME")
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    s3_bucket_name: str | None = Field(default=None, alias="S3_BUCKET_NAME")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_upload_prefix: str = Field(default="conversations", alias="S3_UPLOAD_PREFIX")
    s3_presign_ttl_seconds: int = Field(default=900, alias="S3_PRESIGN_TTL_SECONDS")
    mock_openai: bool = Field(default=False, alias="MOCK_OPENAI")
    agent_provider: str = Field(default="openai", alias="AGENT_PROVIDER")


settings = Settings()

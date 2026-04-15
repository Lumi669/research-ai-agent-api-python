from typing import Literal
from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class AgentChatBody(BaseModel):
    messages: list[AgentMessage] = Field(min_length=1, max_length=50)


class AgentChatData(BaseModel):
    reply: str
    provider: str
    tools_used: list[str] = Field(alias="toolsUsed")

    model_config = {"populate_by_name": True}

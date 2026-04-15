from pydantic import BaseModel, Field

from app.models.agent import AgentChatData, AgentMessage, MessagePart


class CreateConversationBody(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = Field(default=None, alias="systemPrompt", max_length=10_000)

    model_config = {"populate_by_name": True}


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    system_prompt: str | None = Field(alias="systemPrompt")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    message_count: int = Field(alias="messageCount")

    model_config = {"populate_by_name": True}


class ConversationDetail(ConversationSummary):
    messages: list[AgentMessage]


class PostConversationMessageBody(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    parts: list[MessagePart] | None = Field(default=None, max_length=50)


class PostConversationMessageData(BaseModel):
    conversation: ConversationDetail
    assistant: AgentChatData

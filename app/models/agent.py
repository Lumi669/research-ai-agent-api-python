from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator


class TextPart(BaseModel):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=20_000)


class TableData(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=100)
    rows: list[list[str]] = Field(default_factory=list, max_length=1000)


class TablePart(BaseModel):
    type: Literal["table"]
    table: TableData


class ImageData(BaseModel):
    storage: Literal["s3"]
    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=2048)
    mime_type: str = Field(alias="mimeType", min_length=1, max_length=255)
    caption: str | None = Field(default=None, max_length=1000)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)

    model_config = {"populate_by_name": True}


class ImagePart(BaseModel):
    type: Literal["image"]
    image: ImageData


class FileData(BaseModel):
    storage: Literal["s3"]
    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(alias="mimeType", min_length=1, max_length=255)
    size_bytes: int = Field(alias="sizeBytes", ge=0)

    model_config = {"populate_by_name": True}


class FilePart(BaseModel):
    type: Literal["file"]
    file: FileData


MessagePart = Annotated[TextPart | TablePart | ImagePart | FilePart, Field(discriminator="type")]


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    parts: list[MessagePart] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_message_payload(self) -> "AgentMessage":
        if not self.content and not self.parts:
            raise ValueError("Either content or parts is required.")
        return self

    @property
    def text_content(self) -> str:
        if self.content:
            return self.content
        if not self.parts:
            return ""
        rendered_parts: list[str] = []
        for part in self.parts:
            if isinstance(part, TextPart):
                rendered_parts.append(part.text)
            elif isinstance(part, TablePart):
                header = " | ".join(part.table.columns)
                rows = [" | ".join(row) for row in part.table.rows]
                rendered_parts.append("\n".join([header, *rows]).strip())
            elif isinstance(part, ImagePart):
                rendered_parts.append(part.image.caption or f"[image: {part.image.key}]")
            elif isinstance(part, FilePart):
                rendered_parts.append(f"[file: {part.file.name}]")
        return "\n\n".join(fragment for fragment in rendered_parts if fragment).strip()


class AgentChatBody(BaseModel):
    messages: list[AgentMessage] = Field(min_length=1, max_length=50)


class AgentChatData(BaseModel):
    reply: str
    provider: str
    tools_used: list[str] = Field(alias="toolsUsed")

    model_config = {"populate_by_name": True}

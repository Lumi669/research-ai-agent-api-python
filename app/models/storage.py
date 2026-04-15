from typing import Literal

from pydantic import BaseModel, Field

from app.models.agent import FilePart, ImagePart


UploadKind = Literal["image", "file"]


class CreatePresignedUploadBody(BaseModel):
    conversation_id: str = Field(alias="conversationId", min_length=1, max_length=255)
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=255)
    size_bytes: int = Field(alias="sizeBytes", ge=1)
    kind: UploadKind

    model_config = {"populate_by_name": True}


class CreatePresignedUploadData(BaseModel):
    upload_url: str = Field(alias="uploadUrl")
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    bucket: str
    key: str
    expires_in: int = Field(alias="expiresIn")
    part: ImagePart | FilePart

    model_config = {"populate_by_name": True}

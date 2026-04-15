from __future__ import annotations

import asyncio
import os
import re
from functools import lru_cache
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.errors import AppError
from app.models.agent import FilePart, ImagePart, MessagePart
from app.models.storage import CreatePresignedUploadBody, CreatePresignedUploadData


def _normalized_bucket() -> str:
    bucket = (settings.s3_bucket_name or "").strip()
    if not bucket:
        raise AppError(503, "S3_BUCKET_NAME is not configured.")
    return bucket


def _sanitize_filename(file_name: str) -> str:
    base_name = os.path.basename(file_name.strip())
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", base_name).strip("-")
    return sanitized or "upload.bin"


def _conversation_prefix(conversation_id: str) -> str:
    return f"{settings.s3_upload_prefix.strip().strip('/')}/{conversation_id}".strip("/")


@lru_cache(maxsize=1)
def get_s3_client():
    client_kwargs: dict[str, object] = {
        "region_name": settings.aws_region,
        "config": Config(signature_version="s3v4"),
    }
    if (settings.s3_endpoint_url or "").strip():
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url.strip()
    else:
        client_kwargs["endpoint_url"] = f"https://s3.{settings.aws_region}.amazonaws.com"
    return boto3.client("s3", **client_kwargs)


async def create_presigned_upload(body: CreatePresignedUploadBody) -> CreatePresignedUploadData:
    bucket = _normalized_bucket()
    file_name = _sanitize_filename(body.file_name)
    object_key = f"{_conversation_prefix(body.conversation_id)}/{uuid4()}-{file_name}"
    headers = {"Content-Type": body.content_type}

    if body.kind == "image" and not body.content_type.lower().startswith("image/"):
        raise AppError(422, "Image uploads must use an image/* content type.")

    try:
        upload_url = await asyncio.to_thread(
            get_s3_client().generate_presigned_url,
            "put_object",
            Params={"Bucket": bucket, "Key": object_key, "ContentType": body.content_type},
            ExpiresIn=settings.s3_presign_ttl_seconds,
            HttpMethod="PUT",
        )
    except (BotoCoreError, ClientError) as exc:
        raise AppError(502, f"Failed to create presigned upload URL: {exc}") from exc

    if body.kind == "image":
        part = ImagePart(
            type="image",
            image={
                "storage": "s3",
                "bucket": bucket,
                "key": object_key,
                "mimeType": body.content_type,
                "caption": None,
            },
        )
    else:
        part = FilePart(
            type="file",
            file={
                "storage": "s3",
                "bucket": bucket,
                "key": object_key,
                "name": file_name,
                "mimeType": body.content_type,
                "sizeBytes": body.size_bytes,
            },
        )

    return CreatePresignedUploadData(
        uploadUrl=upload_url,
        headers=headers,
        bucket=bucket,
        key=object_key,
        expiresIn=settings.s3_presign_ttl_seconds,
        part=part,
    )


async def validate_s3_message_parts(parts: list[MessagePart] | None, conversation_id: str) -> None:
    if not parts:
        return

    bucket = _normalized_bucket()
    expected_prefix = f"{_conversation_prefix(conversation_id)}/"

    for part in parts:
        if isinstance(part, ImagePart):
            storage_bucket = part.image.bucket
            storage_key = part.image.key
        elif isinstance(part, FilePart):
            storage_bucket = part.file.bucket
            storage_key = part.file.key
        else:
            continue

        if storage_bucket != bucket:
            raise AppError(422, "Attachment bucket does not match the configured S3 bucket.")
        if not storage_key.startswith(expected_prefix):
            raise AppError(422, "Attachment key does not belong to this conversation.")

        try:
            await asyncio.to_thread(get_s3_client().head_object, Bucket=storage_bucket, Key=storage_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise AppError(422, "Referenced S3 object was not found. Upload the file before attaching it.") from exc
            raise AppError(502, f"Failed to validate S3 object: {exc}") from exc
        except BotoCoreError as exc:
            raise AppError(502, f"Failed to validate S3 object: {exc}") from exc

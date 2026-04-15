from functools import lru_cache

import boto3

from app.core.config import settings
from app.core.errors import AppError


@lru_cache(maxsize=1)
def get_dynamodb_table():
    table_name = (settings.dynamodb_table_name or "").strip()
    if not table_name:
        raise AppError(503, "DYNAMODB_TABLE_NAME is not configured.")

    resource_kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if (settings.dynamodb_endpoint_url or "").strip():
        resource_kwargs["endpoint_url"] = settings.dynamodb_endpoint_url.strip()

    dynamodb = boto3.resource("dynamodb", **resource_kwargs)
    return dynamodb.Table(table_name)

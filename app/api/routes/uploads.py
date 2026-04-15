from fastapi import APIRouter, Depends

from app.core.security import require_internal_api_key
from app.models.storage import CreatePresignedUploadBody
from app.services.s3 import create_presigned_upload

router = APIRouter(prefix="/v1/uploads", tags=["uploads"], dependencies=[Depends(require_internal_api_key)])


@router.post("/presign")
async def post_presigned_upload(body: CreatePresignedUploadBody) -> dict:
    return {"success": True, "data": await create_presigned_upload(body)}

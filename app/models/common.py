from pydantic import BaseModel


class SuccessEnvelope(BaseModel):
    success: bool = True

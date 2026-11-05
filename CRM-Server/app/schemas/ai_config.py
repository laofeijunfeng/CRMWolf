"""AI configuration request/response contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StructuredOutputMode = Literal["json_object", "json_schema"]
AssistantVerificationStage = Literal[
    "CONFIGURATION", "ROOT_DECISION", "MEETING_STREAM", "QUALITY_STREAM", "SAVE_VERIFICATION", "COMPLETE",
]
AssistantVerificationCode = Literal[
    "CONFIGURATION_ERROR", "REQUEST_PROTOCOL_ERROR", "AUTHENTICATION_ERROR",
    "UPSTREAM_UNAVAILABLE", "UPSTREAM_TIMEOUT", "MODEL_OUTPUT_INVALID",
    "INTERNAL_ERROR", "CONFIGURATION_CHANGED",
]


class AIConfigCreate(BaseModel):
    api_host: str = Field(..., min_length=1, max_length=255)
    api_key: str = Field(..., max_length=255, description="更新时空值保持现有密钥；新建时必须提供")
    model_name: str = Field(..., min_length=1, max_length=100)
    structured_output_mode: StructuredOutputMode = "json_object"


class AIConfigResponse(BaseModel):
    id: int
    api_host: str
    api_key_masked: str
    model_name: str
    temperature: float
    max_tokens: int
    updated_at: datetime | None = None
    structured_output_mode: StructuredOutputMode = "json_object"
    assistant_verification_state: Literal["UNVERIFIED", "VERIFIED"] = "UNVERIFIED"
    assistant_verified_at: datetime | None = None

    class Config:
        from_attributes = True


class AITestRequest(BaseModel):
    test_message: str = Field(..., min_length=1, max_length=500)


class AITestResponse(BaseModel):
    success: bool
    message: str
    ai_response: str | None = None


class AssistantCapabilityResponse(BaseModel):
    success: bool
    stage: AssistantVerificationStage
    code: AssistantVerificationCode | None = None
    message: str
    output_mode: StructuredOutputMode | None = None
    verified_at: datetime | None = None


class AssistantCapabilityEnvelope(BaseModel):
    code: int = 0
    message: str
    data: AssistantCapabilityResponse
    timestamp: int

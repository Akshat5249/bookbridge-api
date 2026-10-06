"""One JSON envelope for domain, validation and framework errors."""

from pydantic import BaseModel, Field


class ValidationDetail(BaseModel):
    """Safe client-input failure without rejected values or internal paths."""

    field: str
    message: str


class Error(BaseModel):
    """Public error payload."""

    code: str
    message: str
    details: list[ValidationDetail] | None = None


class ErrorResponse(BaseModel):
    """Shared response used even for framework 404/405/422 and unexpected failures."""

    error: Error = Field(
        examples=[
            {
                "code": "NOT_FOUND",
                "message": "The requested resource was not found.",
                "details": None,
            }
        ]
    )

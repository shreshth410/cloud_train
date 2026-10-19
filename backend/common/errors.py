"""CloudTrain domain errors and standard error representations."""

from typing import Any


class CloudTrainError(Exception):
    """Base exception for all CloudTrain errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


class ValidationError(CloudTrainError):
    """Raised when request payload or configuration fails validation."""

    def __init__(
        self,
        message: str = "Configuration is invalid.",
        field_errors: list[dict[str, str]] | None = None,
    ):
        details = {"fields": field_errors} if field_errors else {}
        super().__init__(
            code="VALIDATION_FAILED",
            message=message,
            status_code=400,
            details=details,
        )


class NotFoundError(CloudTrainError):
    """Raised when a requested resource does not exist or does not belong to caller."""

    def __init__(self, message: str = "Resource not found."):
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class ConflictError(CloudTrainError):
    """Raised when a resource state conflicts with the requested action."""

    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=409)


class QuotaExceededError(CloudTrainError):
    """Raised when user limits or quotas are exceeded."""

    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=429)


class InternalError(CloudTrainError):
    """Raised for unexpected internal server errors."""

    def __init__(self, message: str = "An unexpected error occurred."):
        super().__init__(code="INTERNAL_ERROR", message=message, status_code=500)

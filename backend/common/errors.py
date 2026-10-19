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


class InvalidFilenameError(CloudTrainError):
    """Raised when uploaded file name is invalid."""

    def __init__(self, message: str = "Dataset filename must end with .csv"):
        super().__init__(code="INVALID_FILENAME", message=message, status_code=400)


class DatasetInUseError(ConflictError):
    """Raised when deleting a dataset currently in use by active jobs."""

    def __init__(self, message: str = "Cannot delete dataset currently in use by an active training job."):
        super().__init__(code="DATASET_IN_USE", message=message)


class DatasetNotReadyError(ConflictError):
    """Raised when training is attempted on a non-ready dataset."""

    def __init__(self, message: str = "Dataset is not ready for training."):
        super().__init__(code="DATASET_NOT_READY", message=message)


class JobActiveError(ConflictError):
    """Raised when trying to delete an active job."""

    def __init__(self, message: str = "Cannot delete active job."):
        super().__init__(code="JOB_ACTIVE", message=message)


class JobNotSucceededError(ConflictError):
    """Raised when artifacts/results requested for a non-succeeded job."""

    def __init__(self, message: str = "Artifacts/results are only available for SUCCEEDED jobs."):
        super().__init__(code="JOB_NOT_SUCCEEDED", message=message)


class DatasetLimitError(QuotaExceededError):
    """Raised when user dataset quota is exceeded."""

    def __init__(self, message: str = "User dataset limit exceeded."):
        super().__init__(code="DATASET_LIMIT", message=message)


class TooManyActiveJobsError(QuotaExceededError):
    """Raised when user active jobs quota is exceeded."""

    def __init__(self, message: str = "Maximum active jobs limit reached."):
        super().__init__(code="TOO_MANY_ACTIVE_JOBS", message=message)

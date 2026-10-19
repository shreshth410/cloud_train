"""State machine definitions, state ranking, and transition validation."""

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    UPLOADING = "UPLOADING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class DatasetStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    PROFILING = "PROFILING"
    READY = "READY"
    INVALID = "INVALID"


class JobStage(StrEnum):
    BOOTSTRAP = "BOOTSTRAP"
    DOWNLOADING = "DOWNLOADING"
    VALIDATING = "VALIDATING"
    PREPROCESSING = "PREPROCESSING"
    TRAINING = "TRAINING"
    EVALUATING = "EVALUATING"
    EXPLAINING = "EXPLAINING"
    UPLOADING = "UPLOADING"
    DONE = "DONE"


STAGE_PROGRESS: dict[JobStage, int] = {
    JobStage.BOOTSTRAP: 5,
    JobStage.DOWNLOADING: 10,
    JobStage.VALIDATING: 15,
    JobStage.PREPROCESSING: 25,
    JobStage.TRAINING: 50,  # 40-75%
    JobStage.EVALUATING: 80,
    JobStage.EXPLAINING: 88,
    JobStage.UPLOADING: 95,
    JobStage.DONE: 100,
}

JOB_STATUS_RANK: dict[JobStatus, int] = {
    JobStatus.QUEUED: 1,
    JobStatus.PROVISIONING: 2,
    JobStatus.RUNNING: 3,
    JobStatus.UPLOADING: 4,
    JobStatus.SUCCEEDED: 5,
    JobStatus.FAILED: 5,
    JobStatus.CANCELLED: 5,
    JobStatus.TIMED_OUT: 5,
}

TERMINAL_JOB_STATUSES: set[JobStatus] = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.TIMED_OUT,
}

TERMINAL_DATASET_STATUSES: set[DatasetStatus] = {
    DatasetStatus.READY,
    DatasetStatus.INVALID,
}

# Allowed direct transitions: from_status -> set(to_statuses)
ALLOWED_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {
        JobStatus.PROVISIONING,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
    },
    JobStatus.PROVISIONING: {
        JobStatus.RUNNING,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
    },
    JobStatus.RUNNING: {
        JobStatus.UPLOADING,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
    },
    JobStatus.UPLOADING: {
        JobStatus.SUCCEEDED,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
    },
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
    JobStatus.TIMED_OUT: set(),
}

ALLOWED_DATASET_TRANSITIONS: dict[DatasetStatus, set[DatasetStatus]] = {
    DatasetStatus.PENDING_UPLOAD: {
        DatasetStatus.PROFILING,
        DatasetStatus.INVALID,
    },
    DatasetStatus.PROFILING: {
        DatasetStatus.READY,
        DatasetStatus.INVALID,
    },
    DatasetStatus.READY: set(),
    DatasetStatus.INVALID: set(),
}


def is_job_terminal(status: str) -> bool:
    """Check if the given job status is terminal."""
    try:
        job_status = JobStatus(status)
        return job_status in TERMINAL_JOB_STATUSES
    except ValueError:
        return False


def is_dataset_terminal(status: str) -> bool:
    """Check if the given dataset status is terminal."""
    try:
        ds_status = DatasetStatus(status)
        return ds_status in TERMINAL_DATASET_STATUSES
    except ValueError:
        return False


def can_transition(old: str, new: str) -> bool:
    """Check if a job state transition from old to new is allowed.

    Rule: updates may only move forward in rank, terminal states are never overwritten,
    and must be an explicitly allowed transition.
    """
    try:
        old_status = JobStatus(old)
        new_status = JobStatus(new)
    except ValueError:
        return False

    if is_job_terminal(old_status):
        return False

    if JOB_STATUS_RANK[new_status] < JOB_STATUS_RANK[old_status]:
        return False

    return new_status in ALLOWED_JOB_TRANSITIONS.get(old_status, set())


def can_transition_dataset(old: str, new: str) -> bool:
    """Check if a dataset state transition from old to new is allowed."""
    try:
        old_status = DatasetStatus(old)
        new_status = DatasetStatus(new)
    except ValueError:
        return False

    if is_dataset_terminal(old_status):
        return False

    return new_status in ALLOWED_DATASET_TRANSITIONS.get(old_status, set())

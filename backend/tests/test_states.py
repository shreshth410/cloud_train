"""Unit tests for CloudTrain state machine definitions and transition rules."""

from common.states import (
    JOB_STATUS_RANK,
    STAGE_PROGRESS,
    JobStage,
    JobStatus,
    can_transition,
    can_transition_dataset,
    is_dataset_terminal,
    is_job_terminal,
)


def test_job_status_ranks():
    """Verify state ranks: QUEUED 1 < PROVISIONING 2 < RUNNING 3 < UPLOADING 4 < terminal 5."""
    assert JOB_STATUS_RANK[JobStatus.QUEUED] == 1
    assert JOB_STATUS_RANK[JobStatus.PROVISIONING] == 2
    assert JOB_STATUS_RANK[JobStatus.RUNNING] == 3
    assert JOB_STATUS_RANK[JobStatus.UPLOADING] == 4
    assert JOB_STATUS_RANK[JobStatus.SUCCEEDED] == 5
    assert JOB_STATUS_RANK[JobStatus.FAILED] == 5
    assert JOB_STATUS_RANK[JobStatus.CANCELLED] == 5
    assert JOB_STATUS_RANK[JobStatus.TIMED_OUT] == 5


def test_valid_job_transitions():
    """Verify all allowed state transitions succeed."""
    # From QUEUED
    assert can_transition("QUEUED", "PROVISIONING") is True
    assert can_transition("QUEUED", "CANCELLED") is True
    assert can_transition("QUEUED", "FAILED") is True

    # From PROVISIONING
    assert can_transition("PROVISIONING", "RUNNING") is True
    assert can_transition("PROVISIONING", "CANCELLED") is True
    assert can_transition("PROVISIONING", "FAILED") is True
    assert can_transition("PROVISIONING", "TIMED_OUT") is True

    # From RUNNING
    assert can_transition("RUNNING", "UPLOADING") is True
    assert can_transition("RUNNING", "CANCELLED") is True
    assert can_transition("RUNNING", "FAILED") is True
    assert can_transition("RUNNING", "TIMED_OUT") is True

    # From UPLOADING
    assert can_transition("UPLOADING", "SUCCEEDED") is True
    assert can_transition("UPLOADING", "CANCELLED") is True
    assert can_transition("UPLOADING", "FAILED") is True
    assert can_transition("UPLOADING", "TIMED_OUT") is True


def test_terminal_states_cannot_transition():
    """Verify terminal states can never be overwritten or transitioned out of."""
    terminal_states = ["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"]
    all_states = [s.value for s in JobStatus]

    for term in terminal_states:
        assert is_job_terminal(term) is True
        for target in all_states:
            assert can_transition(term, target) is False


def test_disallowed_forward_or_backward_transitions():
    """Verify invalid jumps and backward movements are rejected."""
    # Backward
    assert can_transition("RUNNING", "QUEUED") is False
    assert can_transition("RUNNING", "PROVISIONING") is False
    assert can_transition("UPLOADING", "RUNNING") is False

    # Skipping required steps (e.g., QUEUED directly to SUCCEEDED)
    assert can_transition("QUEUED", "SUCCEEDED") is False
    assert can_transition("QUEUED", "RUNNING") is False
    assert can_transition("PROVISIONING", "SUCCEEDED") is False

    # Invalid names
    assert can_transition("NON_EXISTENT", "RUNNING") is False
    assert can_transition("QUEUED", "NON_EXISTENT") is False


def test_dataset_transitions():
    """Verify dataset state transitions and terminal states."""
    assert can_transition_dataset("PENDING_UPLOAD", "PROFILING") is True
    assert can_transition_dataset("PENDING_UPLOAD", "INVALID") is True
    assert can_transition_dataset("PROFILING", "READY") is True
    assert can_transition_dataset("PROFILING", "INVALID") is True

    # Terminal states cannot transition
    assert is_dataset_terminal("READY") is True
    assert is_dataset_terminal("INVALID") is True
    assert can_transition_dataset("READY", "PROFILING") is False
    assert can_transition_dataset("INVALID", "READY") is False

    # Invalid status names
    assert can_transition_dataset("INVALID_NAME", "READY") is False
    assert can_transition_dataset("PENDING_UPLOAD", "INVALID_NAME") is False
    assert is_dataset_terminal("INVALID_NAME") is False
    assert is_job_terminal("INVALID_NAME") is False


def test_stage_progress_mapping():
    """Verify job stage progress numbers strictly increase."""
    assert STAGE_PROGRESS[JobStage.BOOTSTRAP] == 5
    assert STAGE_PROGRESS[JobStage.DOWNLOADING] == 10
    assert STAGE_PROGRESS[JobStage.VALIDATING] == 15
    assert STAGE_PROGRESS[JobStage.PREPROCESSING] == 25
    assert STAGE_PROGRESS[JobStage.EVALUATING] == 80
    assert STAGE_PROGRESS[JobStage.EXPLAINING] == 88
    assert STAGE_PROGRESS[JobStage.UPLOADING] == 95
    assert STAGE_PROGRESS[JobStage.DONE] == 100

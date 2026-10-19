"""Unit tests for job config validation, resolution, and schema enforcement."""

import pytest

from common.errors import ValidationError
from common.schemas import (
    validate_and_resolve_job_config,
    validate_status_event,
)


@pytest.fixture
def mock_dataset_profile():
    return {
        "row_count": 500,
        "column_count": 5,
        "delimiter": ",",
        "encoding": "utf-8",
        "columns": [
            {
                "name": "age",
                "dtype": "numeric",
                "missing_count": 5,
                "missing_pct": 1.0,
                "unique_count": 60,
            },
            {
                "name": "balance",
                "dtype": "numeric",
                "missing_count": 0,
                "missing_pct": 0.0,
                "unique_count": 450,
            },
            {
                "name": "churn",
                "dtype": "numeric",
                "missing_count": 0,
                "missing_pct": 0.0,
                "unique_count": 2,
            },
            {
                "name": "gender",
                "dtype": "categorical",
                "missing_count": 0,
                "missing_pct": 0.0,
                "unique_count": 2,
            },
            {
                "name": "customer_id",
                "dtype": "id_like",
                "missing_count": 0,
                "missing_pct": 0.0,
                "unique_count": 500,
            },
            {
                "name": "too_many_missing",
                "dtype": "numeric",
                "missing_count": 50,
                "missing_pct": 10.0,
                "unique_count": 30,
            },
        ],
    }


def test_valid_minimal_job_config(mock_dataset_profile):
    """Test minimal job configuration fills defaults properly."""
    raw_config = {
        "name": "Test Job",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "model": {"id": "random_forest"},
    }
    resolved = validate_and_resolve_job_config(raw_config, mock_dataset_profile)

    assert resolved["name"] == "Test Job"
    assert resolved["task"] == "classification"  # churn has 2 unique values -> auto-resolved
    assert resolved["config_version"] == 1
    assert resolved["preprocessing"]["numeric_impute"] == "median"
    assert resolved["preprocessing"]["scale_numeric"] is True
    assert resolved["split"]["test_size"] == 0.2
    assert resolved["cross_validation"]["folds"] == 0
    assert resolved["compute"]["size"] == "small"
    assert resolved["max_runtime_minutes"] == 30
    assert resolved["model"]["hyperparameters"]["n_estimators"] == 100


def test_auto_task_resolution_numeric_regression(mock_dataset_profile):
    """Test auto-resolving regression for continuous numeric target (> 20 unique values)."""
    raw_config = {
        "name": "Regression Job",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "balance",
        "model": {"id": "linear_regression"},
    }
    resolved = validate_and_resolve_job_config(raw_config, mock_dataset_profile)
    assert resolved["task"] == "regression"


def test_target_not_categorical_error(mock_dataset_profile):
    """Test rejection when user forces classification on target with > 50 numeric values."""
    raw_config = {
        "name": "Invalid Cls Job",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "task": "classification",
        "target_column": "balance",  # balance has 450 unique values
        "model": {"id": "logistic_regression"},
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_and_resolve_job_config(raw_config, mock_dataset_profile)

    fields = exc_info.value.details.get("fields", [])
    assert any(f.get("message") == "TARGET_NOT_CATEGORICAL" for f in fields)


def test_target_column_invalid_checks(mock_dataset_profile):
    """Test target column existence, dtype exclusion, and missing value checks."""
    # Non-existent target
    cfg1 = {
        "name": "Missing Target",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "non_existent",
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg1, mock_dataset_profile)

    # Excluded dtype (id_like)
    cfg2 = {
        "name": "Id Target",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "customer_id",
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg2, mock_dataset_profile)

    # Missing > 5%
    cfg3 = {
        "name": "High Missing Target",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "too_many_missing",
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg3, mock_dataset_profile)


def test_hyperparameter_range_validation(mock_dataset_profile):
    """Test validating hyperparameters against min, max, and type constraints."""
    # Out of range (n_estimators too large)
    cfg = {
        "name": "Out of Range",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "model": {
            "id": "random_forest",
            "hyperparameters": {"n_estimators": 9999},
        },
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg, mock_dataset_profile)

    # Unknown hyperparameter
    cfg_unknown = {
        "name": "Unknown Param",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "model": {
            "id": "random_forest",
            "hyperparameters": {"non_existent_param": 10},
        },
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg_unknown, mock_dataset_profile)


def test_feature_columns_validation(mock_dataset_profile):
    """Test feature column selection rules."""
    # Feature includes target column -> error
    cfg = {
        "name": "Feature has Target",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "feature_columns": ["age", "churn"],
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError):
        validate_and_resolve_job_config(cfg, mock_dataset_profile)

    # Valid feature columns subset
    cfg_valid = {
        "name": "Valid Features",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "feature_columns": ["age", "balance"],
        "model": {"id": "random_forest"},
    }
    resolved = validate_and_resolve_job_config(cfg_valid, mock_dataset_profile)
    assert resolved["feature_columns"] == ["age", "balance"]


def test_status_event_validation():
    """Verify validation of status events against status_event.schema.json."""
    valid_event = {
        "job_id": "12345678-1234-5678-1234-567812345678",
        "seq": 1,
        "ts": "2026-10-19T10:15:30Z",
        "event": "STAGE",
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 40,
        "message": "Starting training",
        "payload": {
            "metrics_summary": {"accuracy": 0.95},
        },
    }
    # Should not raise
    validate_status_event(valid_event)

    # Missing required field
    invalid_event = {
        "job_id": "12345678-1234-5678-1234-567812345678",
        "seq": 1,
        "status": "RUNNING",
    }
    with pytest.raises(ValidationError):
        validate_status_event(invalid_event)

    # Invalid progress range
    invalid_progress = dict(valid_event, progress=150)
    with pytest.raises(ValidationError):
        validate_status_event(invalid_progress)


def test_schema_not_found():
    from common.schemas import find_schema_path

    with pytest.raises(FileNotFoundError):
        find_schema_path("completely_imaginary_schema.json")


def test_auto_task_resolution_branches(mock_dataset_profile):
    """Test categorical target resolution and forced regression."""
    # Categorical target auto-resolves to classification
    cfg_cat = {
        "name": "Cat Job",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "gender",
        "model": {"id": "random_forest"},
    }
    resolved = validate_and_resolve_job_config(cfg_cat, mock_dataset_profile)
    assert resolved["task"] == "classification"

    # Explicit regression requested on numeric target
    cfg_reg = {
        "name": "Forced Reg Job",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "task": "regression",
        "target_column": "age",
        "model": {"id": "random_forest"},
    }
    resolved_reg = validate_and_resolve_job_config(cfg_reg, mock_dataset_profile)
    assert resolved_reg["task"] == "regression"


def test_invalid_feature_columns_branches(mock_dataset_profile):
    """Test empty list and non-existent feature columns."""
    # Empty list
    cfg_empty = {
        "name": "Empty Features",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "feature_columns": [],
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_empty, mock_dataset_profile)
    assert any("non-empty list" in f["message"] for f in exc.value.details["fields"])

    # Column not in dataset
    cfg_missing_col = {
        "name": "Missing Col",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "feature_columns": ["not_in_dataset"],
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_missing_col, mock_dataset_profile)
    assert any("does not exist in dataset" in f["message"] for f in exc.value.details["fields"])


def test_model_task_mismatch(mock_dataset_profile):
    """Test model not supporting task (e.g., linear_regression on classification)."""
    cfg = {
        "name": "Mismatch",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",  # auto-resolves to classification
        "model": {"id": "linear_regression"},  # only supports regression
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg, mock_dataset_profile)
    assert any("does not support task" in f["message"] for f in exc.value.details["fields"])


def test_hyperparameter_types_and_bounds(mock_dataset_profile):
    """Exhaustive tests for int, float, enum, and bool hyperparameter validations."""
    base = {
        "name": "HP Test",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
    }

    # Non-nullable null
    cfg_null = dict(base, model={"id": "random_forest", "hyperparameters": {"n_estimators": None}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_null, mock_dataset_profile)
    assert any("cannot be null" in f["message"] for f in exc.value.details["fields"])

    # Int as bool
    cfg_bool_as_int = dict(base, model={"id": "random_forest", "hyperparameters": {"n_estimators": True}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_bool_as_int, mock_dataset_profile)
    assert any("must be an integer" in f["message"] for f in exc.value.details["fields"])

    # Int below min
    cfg_int_min = dict(base, model={"id": "random_forest", "hyperparameters": {"n_estimators": 2}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_int_min, mock_dataset_profile)
    assert any("between" in f["message"] for f in exc.value.details["fields"])

    # Float non-float
    cfg_flt_type = dict(base, model={"id": "xgboost", "hyperparameters": {"learning_rate": "fast"}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_flt_type, mock_dataset_profile)
    assert any("must be a float" in f["message"] for f in exc.value.details["fields"])

    # Float below min
    cfg_flt_min = dict(base, model={"id": "xgboost", "hyperparameters": {"learning_rate": 0.0001}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_flt_min, mock_dataset_profile)
    assert any("between" in f["message"] for f in exc.value.details["fields"])

    # Float above max
    cfg_flt_max = dict(base, model={"id": "xgboost", "hyperparameters": {"learning_rate": 5.0}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_flt_max, mock_dataset_profile)
    assert any("between" in f["message"] for f in exc.value.details["fields"])

    # Enum invalid option
    cfg_enum = dict(base, model={"id": "knn", "hyperparameters": {"weights": "invalid_option"}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_enum, mock_dataset_profile)
    assert any("must be one of" in f["message"] for f in exc.value.details["fields"])

    # Int above max (min_samples_split max is 50 for decision_tree)
    cfg_dt_max = dict(base, model={"id": "decision_tree", "hyperparameters": {"min_samples_split": 999}})
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_dt_max, mock_dataset_profile)
    assert any("between" in f["message"] for f in exc.value.details["fields"])


def test_schema_top_level_and_unknown_model_errors(mock_dataset_profile):
    """Test top-level schema validation errors and unknown model id."""
    # Missing required 'name'
    cfg_no_name = {
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_no_name, mock_dataset_profile)
    assert len(exc.value.details["fields"]) > 0

    # Unknown model id
    cfg_unknown = {
        "name": "Unknown Model",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "model": {"id": "non_existent_model"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg_unknown, mock_dataset_profile)
    assert len(exc.value.details["fields"]) > 0


def test_target_in_feature_columns_error(mock_dataset_profile):
    """Test validation fails when target column is inside feature_columns list."""
    cfg = {
        "name": "Target In Features",
        "dataset_id": "12345678-1234-5678-1234-567812345678",
        "target_column": "churn",
        "feature_columns": ["age", "churn"],
        "model": {"id": "random_forest"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_and_resolve_job_config(cfg, mock_dataset_profile)
    assert any("must not include target" in f["message"] for f in exc.value.details["fields"])


def test_single_hyperparameter_bool_and_resolve_task():
    """Test bool hyperparameter branch and task resolution non-numeric."""
    from common.schemas import _validate_single_hyperparameter, resolve_task_type

    spec_bool = {"name": "fit_intercept", "type": "bool", "default": True}
    _validate_single_hyperparameter("model", "fit_intercept", True, spec_bool)
    with pytest.raises(ValidationError) as exc:
        _validate_single_hyperparameter("model", "fit_intercept", "not_bool", spec_bool)
    assert any("must be a boolean" in f["message"] for f in exc.value.details["fields"])

    res = resolve_task_type({"name": "cat_col", "dtype": "categorical", "unique_count": 5}, "auto")
    assert res == "classification"

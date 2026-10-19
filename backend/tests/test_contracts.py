"""Tests for shared contracts: model registry and JSON schemas."""

import jsonschema
import pytest

from common.registry import (
    get_model_class,
    get_model_spec,
    list_models,
    load_registry,
    validate_registry,
)
from common.schemas import load_schema


def test_model_registry_validity():
    """Verify model_registry.json adheres to all structural and domain rules."""
    registry = load_registry(force_reload=True)
    assert registry.get("version") == 1
    models = registry.get("models", [])
    assert len(models) >= 7

    # Validate all models and class imports
    validate_registry(registry)


@pytest.mark.parametrize(
    "model_id,task,expected_class",
    [
        ("logistic_regression", "classification", "LogisticRegression"),
        ("linear_regression", "regression", "LinearRegression"),
        ("ridge", "regression", "Ridge"),
        ("decision_tree", "classification", "DecisionTreeClassifier"),
        ("decision_tree", "regression", "DecisionTreeRegressor"),
        ("random_forest", "classification", "RandomForestClassifier"),
        ("random_forest", "regression", "RandomForestRegressor"),
        ("xgboost", "classification", "XGBClassifier"),
        ("xgboost", "regression", "XGBRegressor"),
        ("knn", "classification", "KNeighborsClassifier"),
        ("knn", "regression", "KNeighborsRegressor"),
    ],
)
def test_all_model_classes_importable(model_id, task, expected_class):
    """Assert every model class in class_path can be imported and matches the expected type."""
    cls = get_model_class(model_id, task)
    assert cls.__name__ == expected_class


def test_model_filtering_by_task():
    """Test listing models filtered by task."""
    cls_models = list_models(task="classification")
    reg_models = list_models(task="regression")

    cls_ids = {m["id"] for m in cls_models}
    reg_ids = {m["id"] for m in reg_models}

    assert "logistic_regression" in cls_ids
    assert "logistic_regression" not in reg_ids

    assert "linear_regression" in reg_ids
    assert "linear_regression" not in cls_ids

    assert "random_forest" in cls_ids
    assert "random_forest" in reg_ids


def test_job_config_schema_is_valid_json_schema():
    """Verify job_config.schema.json is a valid JSON schema draft."""
    schema = load_schema("job_config.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_status_event_schema_is_valid_json_schema():
    """Verify status_event.schema.json is a valid JSON schema draft."""
    schema = load_schema("status_event.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_registry_error_handling():
    """Test registry functions handling unknown models and unsupported tasks."""
    assert get_model_spec("unknown_model_id") is None

    with pytest.raises(ValueError, match="Unknown model id"):
        get_model_class("unknown_model_id", "classification")

    with pytest.raises(ValueError, match="does not support task"):
        get_model_class("logistic_regression", "regression")


def test_validate_registry_with_custom_structures():
    """Test registry validator on custom registry structures including bool and null types."""
    custom_registry = {
        "version": 1,
        "models": [
            {
                "id": "mock_model",
                "display_name": "Mock Model",
                "tasks": ["classification"],
                "class_path": "sklearn.linear_model.LogisticRegression",
                "hyperparameters": [
                    {"name": "flag", "type": "bool", "default": True},
                    {"name": "rate", "type": "float", "min": 0.0, "max": 1.0, "default": 0.5},
                    {"name": "opt", "type": "enum", "options": ["a", "b"], "default": "a"},
                    {"name": "nullable_param", "type": "int", "default": None, "nullable": True},
                ],
            }
        ],
    }
    validate_registry(custom_registry)

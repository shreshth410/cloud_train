"""JSON Schema validation and job configuration resolution."""

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema

from common.errors import ValidationError
from common.registry import get_model_spec


def find_schema_path(filename: str) -> Path:
    """Locate schema files across development and Lambda packaging environments."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "shared" / filename,
        Path(__file__).resolve().parent / filename,
        Path(f"shared/{filename}"),
        Path(f"/var/task/shared/{filename}"),
        Path(f"/var/task/{filename}"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find schema file '{filename}' in candidate locations.")


_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def load_schema(filename: str) -> dict[str, Any]:
    """Load and cache a JSON schema."""
    if filename not in _SCHEMA_CACHE:
        path = find_schema_path(filename)
        with open(path, encoding="utf-8") as f:
            _SCHEMA_CACHE[filename] = json.load(f)
    return _SCHEMA_CACHE[filename]


def validate_status_event(event_dict: dict[str, Any]) -> None:
    """Validate a container status event against shared/status_event.schema.json."""
    schema = load_schema("status_event.schema.json")
    try:
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(event_dict))
        if errors:
            field_errors = []
            for err in errors:
                path = ".".join(str(p) for p in err.absolute_path) or "root"
                field_errors.append({"path": path, "message": err.message})
            raise ValidationError(
                message="Status event validation failed.",
                field_errors=field_errors,
            )
    except jsonschema.ValidationError as exc:
        path = ".".join(str(p) for p in exc.absolute_path) or "root"
        raise ValidationError(
            message="Status event validation failed.",
            field_errors=[{"path": path, "message": exc.message}],
        ) from exc


def resolve_task_type(target_col_info: dict[str, Any], requested_task: str) -> str:
    """Resolve the task type (auto -> classification or regression) and check constraints.

    Rules:
    - target dtype=numeric with unique_count > 20 (or stats/float values) => regression;
      otherwise classification.
    - If user forced 'classification' on a numeric target with > 50 unique values => reject (TARGET_NOT_CATEGORICAL).
    """
    dtype = target_col_info.get("dtype", "categorical")
    unique_count = target_col_info.get("unique_count", 0)

    is_numeric = dtype == "numeric"

    if requested_task == "classification":
        if is_numeric and unique_count > 50:
            raise ValidationError(
                message=f"Target column '{target_col_info.get('name')}' has {unique_count} numeric values and cannot be used for classification.",
                field_errors=[
                    {
                        "path": "task",
                        "message": "TARGET_NOT_CATEGORICAL",
                    }
                ],
            )
        return "classification"

    if requested_task == "regression":
        return "regression"

    # requested_task == "auto"
    if is_numeric and unique_count > 20:
        return "regression"
    return "classification"


def validate_and_resolve_job_config(
    config_dict: dict[str, Any],
    dataset_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate job config against JSON schema and domain rules, and resolve defaults.

    Fills in hyperparameter defaults and auto-config options.
    """
    schema = load_schema("job_config.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(config_dict))

    field_errors: list[dict[str, str]] = []
    if errors:
        for err in errors:
            path = ".".join(str(p) for p in err.absolute_path) or "root"
            field_errors.append({"path": path, "message": err.message})
        raise ValidationError(field_errors=field_errors)

    resolved = copy.deepcopy(config_dict)

    # Defaults for top-level structures
    resolved.setdefault("config_version", 1)
    resolved.setdefault("task", "auto")
    resolved.setdefault("feature_columns", None)
    resolved.setdefault("max_runtime_minutes", 30)

    # Preprocessing defaults
    prep = resolved.setdefault("preprocessing", {})
    prep.setdefault("numeric_impute", "median")
    prep.setdefault("categorical_impute", "most_frequent")
    prep.setdefault("scale_numeric", True)
    prep.setdefault("max_categories", 50)
    prep.setdefault("drop_id_like", True)

    # Split defaults
    split = resolved.setdefault("split", {})
    split.setdefault("test_size", 0.2)
    split.setdefault("stratify", True)
    split.setdefault("random_state", 42)

    # Cross validation defaults
    cv = resolved.setdefault("cross_validation", {})
    cv.setdefault("folds", 0)

    # Compute defaults
    compute = resolved.setdefault("compute", {})
    compute.setdefault("size", "small")

    # Validate dataset profile if provided
    columns_map: dict[str, dict[str, Any]] = {}
    if dataset_profile:
        for col in dataset_profile.get("columns", []):
            columns_map[col["name"]] = col

        target_col = resolved["target_column"]
        if target_col not in columns_map:
            raise ValidationError(
                field_errors=[
                    {
                        "path": "target_column",
                        "message": f"Target column '{target_col}' not found in dataset.",
                    }
                ]
            )

        target_info = columns_map[target_col]
        target_dtype = target_info.get("dtype")
        if target_dtype in {"constant", "id_like", "text", "datetime"}:
            raise ValidationError(
                field_errors=[
                    {
                        "path": "target_column",
                        "message": f"Target column '{target_col}' has invalid dtype '{target_dtype}'.",
                    }
                ]
            )

        missing_pct = target_info.get("missing_pct", 0)
        if missing_pct > 5.0:
            raise ValidationError(
                field_errors=[
                    {
                        "path": "target_column",
                        "message": f"Target column '{target_col}' has {missing_pct}% missing values (maximum allowed is 5%).",
                    }
                ]
            )

        resolved["task"] = resolve_task_type(target_info, resolved["task"])

        # Validate feature columns if provided
        features = resolved.get("feature_columns")
        if features is not None:
            if not features:
                raise ValidationError(
                    field_errors=[
                        {
                            "path": "feature_columns",
                            "message": "feature_columns must be null or a non-empty list of columns.",
                        }
                    ]
                )
            if target_col in features:
                raise ValidationError(
                    field_errors=[
                        {
                            "path": "feature_columns",
                            "message": "feature_columns must not include target column.",
                        }
                    ]
                )
            for col_name in features:
                if col_name not in columns_map:
                    raise ValidationError(
                        field_errors=[
                            {
                                "path": f"feature_columns.{col_name}",
                                "message": f"Feature column '{col_name}' does not exist in dataset.",
                            }
                        ]
                    )

    # Model and hyperparameter validation
    model_obj = resolved["model"]
    model_id = model_obj["id"]
    spec = get_model_spec(model_id)
    if not spec:
        raise ValidationError(
            field_errors=[
                {
                    "path": "model.id",
                    "message": f"Unknown model id '{model_id}'.",
                }
            ]
        )

    task = resolved.get("task")
    if task != "auto" and task not in spec.get("tasks", []):
        raise ValidationError(
            field_errors=[
                {
                    "path": "model.id",
                    "message": f"Model '{model_id}' does not support task '{task}'.",
                }
            ]
        )

    if spec.get("needs_scaling", False):
        resolved["preprocessing"]["scale_numeric"] = True

    # Validate and fill hyperparameters
    user_hparams = model_obj.get("hyperparameters", {})
    spec_hparams = {hp["name"]: hp for hp in spec.get("hyperparameters", [])}

    resolved_hparams: dict[str, Any] = {}
    for hp_name, val in user_hparams.items():
        if hp_name not in spec_hparams:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{hp_name}",
                        "message": f"Unknown hyperparameter '{hp_name}' for model '{model_id}'.",
                    }
                ]
            )
        hp_spec = spec_hparams[hp_name]
        _validate_single_hyperparameter(model_id, hp_name, val, hp_spec)
        resolved_hparams[hp_name] = val

    # Fill default hyperparameters
    for hp_name, hp_spec in spec_hparams.items():
        if hp_name not in resolved_hparams:
            resolved_hparams[hp_name] = hp_spec.get("default")

    model_obj["hyperparameters"] = resolved_hparams
    return resolved


def _validate_single_hyperparameter(
    model_id: str,
    name: str,
    val: Any,
    spec: dict[str, Any],
) -> None:
    """Validate a single hyperparameter value against its specification."""
    nullable = spec.get("nullable", False)
    if val is None:
        if not nullable:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"Hyperparameter '{name}' cannot be null.",
                    }
                ]
            )
        return

    hp_type = spec["type"]
    if hp_type == "int":
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"Hyperparameter '{name}' must be an integer.",
                    }
                ]
            )
        if "min" in spec and val < spec["min"]:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"must be between {spec['min']} and {spec.get('max')}",
                    }
                ]
            )
        if "max" in spec and val > spec["max"]:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"must be between {spec.get('min')} and {spec['max']}",
                    }
                ]
            )

    elif hp_type == "float":
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"Hyperparameter '{name}' must be a float.",
                    }
                ]
            )
        if "min" in spec and val < spec["min"]:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"must be between {spec['min']} and {spec.get('max')}",
                    }
                ]
            )
        if "max" in spec and val > spec["max"]:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"must be between {spec.get('min')} and {spec['max']}",
                    }
                ]
            )

    elif hp_type == "enum":
        options = spec.get("options", [])
        if val not in options:
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"Hyperparameter '{name}' must be one of {options}.",
                    }
                ]
            )

    elif hp_type == "bool":
        if not isinstance(val, bool):
            raise ValidationError(
                field_errors=[
                    {
                        "path": f"model.hyperparameters.{name}",
                        "message": f"Hyperparameter '{name}' must be a boolean.",
                    }
                ]
            )

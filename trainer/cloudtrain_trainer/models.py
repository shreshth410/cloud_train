"""Estimator instantiation from model registry definitions."""

import importlib
import inspect
from typing import Any

from cloudtrain_trainer.config import find_shared_file


def create_estimator(
    model_cfg: dict[str, Any],
    task: str,
    n_classes: int | None = None,
    random_state: int = 42,
) -> Any:
    """Instantiate a model estimator from registry spec and job hyperparameters."""
    import json

    registry_path = find_shared_file("model_registry.json")
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    model_id = model_cfg["id"]
    spec = None
    for m in registry.get("models", []):
        if m["id"] == model_id:
            spec = m
            break
    if not spec:
        raise ValueError(f"Unknown model id: {model_id}")

    # Resolve class path
    class_path_entry = spec["class_path"]
    full_path = class_path_entry[task] if isinstance(class_path_entry, dict) else str(class_path_entry)

    module_name, class_name = full_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    # Combine fixed_params and user hyperparameters
    params = dict(spec.get("fixed_params", {}))
    user_hp = model_cfg.get("hyperparameters", {})
    params.update(user_hp)

    # Filter out None values for parameters that cannot be None
    params = {k: v for k, v in params.items() if v is not None}

    # Inspect estimator constructor signature
    sig = inspect.signature(cls.__init__)
    valid_params = set(sig.parameters.keys())

    # Add random_state if supported
    if "random_state" in valid_params:
        params["random_state"] = random_state

    # Multiclass XGBoost configuration
    if model_id == "xgboost" and task == "classification" and n_classes and n_classes > 2:
        params["objective"] = "multi:softprob"
        params["num_class"] = n_classes

    # Filter params to only those accepted by the constructor
    filtered_params = {k: v for k, v in params.items() if k in valid_params}

    return cls(**filtered_params)

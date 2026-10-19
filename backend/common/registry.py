"""Model registry loader, accessor, and validation functions."""

import importlib
import json
from pathlib import Path
from typing import Any


def find_registry_path() -> Path:
    """Find the model_registry.json file across multiple possible environments."""
    # Check current directory, repo root, or relative to this file
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "shared" / "model_registry.json",
        Path(__file__).resolve().parent / "model_registry.json",
        Path("shared/model_registry.json"),
        Path("/var/task/shared/model_registry.json"),
        Path("/var/task/model_registry.json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not find shared/model_registry.json in candidate locations.")


_REGISTRY_CACHE: dict[str, Any] | None = None


def load_registry(force_reload: bool = False) -> dict[str, Any]:
    """Load and cache the model registry."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None or force_reload:
        path = find_registry_path()
        with open(path, encoding="utf-8") as f:
            _REGISTRY_CACHE = json.load(f)
    return _REGISTRY_CACHE


def list_models(task: str | None = None) -> list[dict[str, Any]]:
    """List models, optionally filtered by supported task (classification or regression)."""
    registry = load_registry()
    models = registry.get("models", [])
    if task:
        return [m for m in models if task in m.get("tasks", [])]
    return models


def get_model_spec(model_id: str, registry_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Get the registry spec for a specific model id."""
    registry = registry_data or load_registry()
    for model in registry.get("models", []):
        if model["id"] == model_id:
            return model
    return None


def get_model_class(model_id: str, task: str, registry_data: dict[str, Any] | None = None) -> Any:
    """Import and return the Python class for the specified model and task."""
    spec = get_model_spec(model_id, registry_data=registry_data)
    if not spec:
        raise ValueError(f"Unknown model id: '{model_id}'")
    if task not in spec.get("tasks", []):
        raise ValueError(f"Model '{model_id}' does not support task '{task}'")

    class_path_entry = spec["class_path"]
    if isinstance(class_path_entry, dict):
        full_path = class_path_entry.get(task)
        if not full_path:
            raise ValueError(f"No class path configured for model '{model_id}' and task '{task}'")
    else:
        full_path = str(class_path_entry)

    module_name, class_name = full_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def validate_registry(registry_data: dict[str, Any] | None = None) -> None:
    """Validate that every class_path in the registry imports and every default is valid."""
    data = registry_data or load_registry()
    assert "models" in data, "Registry must contain 'models' list"
    assert len(data["models"]) >= 1, "Registry must contain at least one model"

    for model in data["models"]:
        model_id = model["id"]
        tasks = model["tasks"]

        # Validate class_paths import properly
        for task in tasks:
            cls = get_model_class(model_id, task, registry_data=data)
            assert cls is not None, f"Could not load class for {model_id} on task {task}"

        # Validate hyperparameters
        for hp in model.get("hyperparameters", []):
            name = hp["name"]
            hp_type = hp["type"]
            default = hp.get("default")
            nullable = hp.get("nullable", False)

            if default is None:
                assert nullable, f"Model {model_id} param {name} default is None but nullable is False"
                continue

            if hp_type == "int":
                assert isinstance(default, int), f"{model_id}.{name} default {default} not int"
                if "min" in hp:
                    assert default >= hp["min"], f"{model_id}.{name} default < min"
                if "max" in hp:
                    assert default <= hp["max"], f"{model_id}.{name} default > max"
            elif hp_type == "float":
                assert isinstance(default, (int, float)), f"{model_id}.{name} default {default} not float"
                if "min" in hp:
                    assert default >= hp["min"], f"{model_id}.{name} default < min"
                if "max" in hp:
                    assert default <= hp["max"], f"{model_id}.{name} default > max"
            elif hp_type == "enum":
                options = hp.get("options", [])
                assert default in options, f"{model_id}.{name} default {default} not in options {options}"
            elif hp_type == "bool":
                assert isinstance(default, bool), f"{model_id}.{name} default {default} not bool"

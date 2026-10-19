"""Section 12.4 tests for CloudTrain model trainer."""

import json
import subprocess
import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest

from cloudtrain_trainer.main import run_pipeline


@pytest.fixture
def samples_dir():
    return Path(__file__).resolve().parent.parent.parent / "samples"


@pytest.fixture
def tmp_output(tmp_path):
    out = tmp_path / "artifacts"
    out.mkdir()
    return out


# ──────────────────────────────────────────────
# (a) Iris Classification (RF, XGB, LR, kNN, Tree)
# ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "model_id",
    [
        "random_forest",
        "xgboost",
        "logistic_regression",
        "knn",
        "decision_tree",
    ],
)
def test_iris_classification_models(model_id, samples_dir, tmp_path):
    """Test Iris classification for all supported classification models."""
    config = {
        "name": f"Iris {model_id}",
        "dataset_id": "iris-uuid",
        "target_column": "target",
        "task": "classification",
        "model": {"id": model_id},
        "split": {"test_size": 0.2, "random_state": 42},
    }
    cfg_path = tmp_path / f"config_{model_id}.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    out_dir = tmp_path / f"out_{model_id}"
    exit_code = run_pipeline(
        user_id="user-test",
        job_id=f"job-{model_id}",
        local_config_path=str(cfg_path),
        local_csv_path=str(samples_dir / "iris.csv"),
        local_output_dir=str(out_dir),
    )
    assert exit_code == 0

    # Verify artifacts exist
    assert (out_dir / "model.joblib").is_file()
    assert (out_dir / "metrics.json").is_file()
    assert (out_dir / "feature_importance.json").is_file()
    assert (out_dir / "model_card.md").is_file()

    # (g) Metrics against known threshold (iris accuracy >= 0.9)
    with open(out_dir / "metrics.json", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["accuracy"] >= 0.90, f"Expected accuracy >= 0.9, got {metrics['accuracy']}"


# ──────────────────────────────────────────────
# (b) Diabetes Regression (all regression models)
# ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "model_id",
    [
        "linear_regression",
        "ridge",
        "decision_tree",
        "random_forest",
        "xgboost",
        "knn",
    ],
)
def test_diabetes_regression_models(model_id, samples_dir, tmp_path):
    """Test Diabetes regression across all regression models."""
    config = {
        "name": f"Diabetes {model_id}",
        "dataset_id": "diabetes-uuid",
        "target_column": "target",
        "task": "regression",
        "model": {"id": model_id},
        "split": {"test_size": 0.2, "random_state": 42},
    }
    cfg_path = tmp_path / f"config_reg_{model_id}.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    out_dir = tmp_path / f"out_reg_{model_id}"
    exit_code = run_pipeline(
        user_id="user-test",
        job_id=f"job-reg-{model_id}",
        local_config_path=str(cfg_path),
        local_csv_path=str(samples_dir / "diabetes.csv"),
        local_output_dir=str(out_dir),
    )
    assert exit_code == 0

    with open(out_dir / "metrics.json", encoding="utf-8") as f:
        metrics = json.load(f)
    assert "r2" in metrics
    assert "rmse" in metrics
    assert "mae" in metrics


# ──────────────────────────────────────────────
# (c) Messy Churn Exclusions Report
# ──────────────────────────────────────────────
def test_messy_churn_exclusions_report(samples_dir, tmp_path):
    """Test preprocessing report correctly identifies constant, id_like, and missing exclusions."""
    config = {
        "name": "Messy Churn Job",
        "dataset_id": "churn-uuid",
        "target_column": "churn",
        "task": "classification",
        "model": {"id": "random_forest", "hyperparameters": {"n_estimators": 50}},
        "preprocessing": {
            "drop_id_like": True,
            "max_categories": 20,
        },
        "cross_validation": {"folds": 3},
    }
    cfg_path = tmp_path / "config_churn.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    out_dir = tmp_path / "out_churn"
    exit_code = run_pipeline(
        user_id="user-test",
        job_id="job-churn",
        local_config_path=str(cfg_path),
        local_csv_path=str(samples_dir / "messy_churn.csv"),
        local_output_dir=str(out_dir),
    )
    assert exit_code == 0

    with open(out_dir / "preprocessing_report.json", encoding="utf-8") as f:
        prep_report = json.load(f)

    excluded = prep_report.get("excluded_columns", {})
    # customer_id should be excluded as id_like
    assert "customer_id" in excluded
    # currency should be excluded as constant
    assert "currency" in excluded
    # signup_date was expanded
    assert "signup_date" in prep_report.get("datetime_columns_expanded", [])


# ──────────────────────────────────────────────
# (d) Failure Cases & Error Codes
# ──────────────────────────────────────────────
def test_failure_cases(tmp_path):
    """Assert failure cases produce the correct status and error codes."""
    # 1. Missing target
    df = pd.DataFrame({"col_a": range(30), "col_b": range(30)})
    csv_missing_target = tmp_path / "missing_target.csv"
    df.to_csv(csv_missing_target, index=False)

    cfg = {
        "name": "Missing Target",
        "dataset_id": "d1",
        "target_column": "non_existent",
        "model": {"id": "random_forest"},
    }
    cfg_p = tmp_path / "cfg_missing_target.json"
    with open(cfg_p, "w", encoding="utf-8") as f:
        json.dump(cfg, f)

    assert (
        run_pipeline(
            user_id="u",
            job_id="j",
            local_config_path=str(cfg_p),
            local_csv_path=str(csv_missing_target),
            local_output_dir=str(tmp_path / "out_fail1"),
        )
        == 1
    )

    # 2. Constant target
    df_const = pd.DataFrame({"feat": range(30), "target": [1] * 30})
    csv_const_target = tmp_path / "const_target.csv"
    df_const.to_csv(csv_const_target, index=False)

    cfg_const = {
        "name": "Const Target",
        "dataset_id": "d2",
        "target_column": "target",
        "task": "classification",
        "model": {"id": "random_forest"},
    }
    cfg_p_const = tmp_path / "cfg_const.json"
    with open(cfg_p_const, "w", encoding="utf-8") as f:
        json.dump(cfg_const, f)

    assert (
        run_pipeline(
            user_id="u",
            job_id="j",
            local_config_path=str(cfg_p_const),
            local_csv_path=str(csv_const_target),
            local_output_dir=str(tmp_path / "out_fail2"),
        )
        == 1
    )

    # 3. Too few rows (< 20 rows)
    df_short = pd.DataFrame({"feat": range(10), "target": [0, 1] * 5})
    csv_short = tmp_path / "short.csv"
    df_short.to_csv(csv_short, index=False)

    cfg_short = {
        "name": "Short DF",
        "dataset_id": "d3",
        "target_column": "target",
        "model": {"id": "random_forest"},
    }
    cfg_p_short = tmp_path / "cfg_short.json"
    with open(cfg_p_short, "w", encoding="utf-8") as f:
        json.dump(cfg_short, f)

    assert (
        run_pipeline(
            user_id="u",
            job_id="j",
            local_config_path=str(cfg_p_short),
            local_csv_path=str(csv_short),
            local_output_dir=str(tmp_path / "out_fail3"),
        )
        == 1
    )


# ──────────────────────────────────────────────
# (f) Produced model.joblib loads and predict_example.py runs
# ──────────────────────────────────────────────
def test_produced_model_and_predict_example(samples_dir, tmp_path):
    """Verify that model.joblib loads and predict_example.py executes offline."""
    config = {
        "name": "Iris Offline Predict",
        "dataset_id": "iris-offline",
        "target_column": "target",
        "task": "classification",
        "model": {"id": "random_forest"},
    }
    cfg_p = tmp_path / "cfg_offline.json"
    with open(cfg_p, "w", encoding="utf-8") as f:
        json.dump(config, f)

    out_dir = tmp_path / "out_offline"
    exit_code = run_pipeline(
        user_id="u",
        job_id="j",
        local_config_path=str(cfg_p),
        local_csv_path=str(samples_dir / "iris.csv"),
        local_output_dir=str(out_dir),
    )
    assert exit_code == 0

    # 1. Load joblib
    model_pkg = joblib.load(out_dir / "model.joblib")
    assert "pipeline" in model_pkg
    assert "meta" in model_pkg
    assert model_pkg["meta"]["task"] == "classification"
    assert "setosa" in model_pkg["meta"]["label_classes"]

    # 2. Run predict_example.py
    pred_csv = tmp_path / "preds.csv"
    cmd = [
        sys.executable,
        str(out_dir / "predict_example.py"),
        "--model",
        str(out_dir / "model.joblib"),
        "--data",
        str(samples_dir / "iris.csv"),
        "--output",
        str(pred_csv),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"predict_example failed: {res.stderr}"
    assert pred_csv.is_file()

    preds_df = pd.read_csv(pred_csv)
    assert "prediction" in preds_df.columns
    assert len(preds_df) == 150

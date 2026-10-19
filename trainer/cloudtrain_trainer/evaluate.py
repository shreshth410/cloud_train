"""Model evaluation, metrics computation, and performance summaries."""

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    median_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    roc_curve,
    root_mean_squared_error,
)


def evaluate_model(
    pipeline: Any,
    X_train: Any,
    X_test: Any,
    y_train: np.ndarray,
    y_test: np.ndarray,
    task: str,
    label_classes: list[str] | None = None,
    fit_seconds: float = 0.0,
    cv_scores: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute detailed evaluation metrics on held-out test split.

    Returns (full_metrics_dict, headline_summary_dict).
    """
    y_pred = pipeline.predict(X_test)
    n_features = 0
    if hasattr(pipeline.named_steps["pre"], "get_feature_names_out"):
        try:
            n_features = len(pipeline.named_steps["pre"].get_feature_names_out())
        except Exception:
            n_features = 0

    metrics: dict[str, Any] = {
        "task": task,
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "n_features_after_encoding": n_features,
        "fit_seconds": round(fit_seconds, 3),
        "cv": cv_scores or {},
    }

    if task == "classification":
        acc = float(accuracy_score(y_test, y_pred))
        bal_acc = float(balanced_accuracy_score(y_test, y_pred))
        p_weighted = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
        r_weighted = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
        f1_weighted = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
        p_macro = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
        r_macro = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
        f1_macro = float(f1_score(y_test, y_pred, average="macro", zero_division=0))

        # Majority class baseline accuracy
        majority_count = max(np.bincount(y_train)) if len(y_train) > 0 else 0
        baseline_acc = float(majority_count / len(y_train)) if len(y_train) > 0 else 0.0
        metrics["baseline"] = {"majority_class_accuracy": round(baseline_acc, 4)}

        # Confusion Matrix
        cm = confusion_matrix(y_test, y_pred)
        classes_str = label_classes or [str(i) for i in range(len(cm))]
        metrics["confusion_matrix"] = {
            "matrix": cm.tolist(),
            "classes": classes_str,
        }

        # Classification Report
        cls_rep = classification_report(
            y_test,
            y_pred,
            target_names=classes_str,
            output_dict=True,
            zero_division=0,
        )
        metrics["classification_report"] = cls_rep

        # ROC AUC & Curves
        roc_auc_val: float | None = None
        roc_curve_data: dict[str, Any] | None = None

        if hasattr(pipeline, "predict_proba"):
            try:
                y_prob = pipeline.predict_proba(X_test)
                n_classes = len(classes_str)

                if n_classes == 2:
                    # Binary ROC AUC
                    roc_auc_val = float(roc_auc_score(y_test, y_prob[:, 1]))
                    fpr, tpr, thresholds = roc_curve(y_test, y_prob[:, 1])

                    # Subsample curve points to <= 100 points
                    if len(fpr) > 100:
                        indices = np.linspace(0, len(fpr) - 1, 100, dtype=int)
                        fpr = fpr[indices]
                        tpr = tpr[indices]
                        thresholds = thresholds[indices]

                    roc_curve_data = {
                        "fpr": [round(float(x), 4) for x in fpr],
                        "tpr": [round(float(x), 4) for x in tpr],
                        "thresholds": [round(float(x), 4) for x in thresholds],
                    }
                elif n_classes > 2:
                    # Multiclass ROC AUC (OvR)
                    roc_auc_val = float(roc_auc_score(y_test, y_prob, multi_class="ovr", average="weighted"))
            except Exception:
                roc_auc_val = None

        metrics.update(
            {
                "accuracy": round(acc, 4),
                "balanced_accuracy": round(bal_acc, 4),
                "precision_weighted": round(p_weighted, 4),
                "recall_weighted": round(r_weighted, 4),
                "f1_weighted": round(f1_weighted, 4),
                "precision_macro": round(p_macro, 4),
                "recall_macro": round(r_macro, 4),
                "f1_macro": round(f1_macro, 4),
                "roc_auc": round(roc_auc_val, 4) if roc_auc_val is not None else None,
                "roc_curve": roc_curve_data,
            }
        )

        summary: dict[str, Any] = {
            "accuracy": round(acc, 4),
            "f1_weighted": round(f1_weighted, 4),
        }
        if roc_auc_val is not None:
            summary["roc_auc"] = round(roc_auc_val, 4)

    else:
        # Regression
        r2 = float(r2_score(y_test, y_pred))
        mae = float(mean_absolute_error(y_test, y_pred))
        rmse = float(root_mean_squared_error(y_test, y_pred))
        med_ae = float(median_absolute_error(y_test, y_pred))

        metrics["baseline"] = {"mean_predictor_r2": 0.0}

        # Predictions sample (up to 500 pairs)
        indices = np.arange(len(y_test))
        if len(y_test) > 500:
            indices = np.random.choice(indices, size=500, replace=False)

        preds_sample = [
            {"actual": round(float(y_test[i]), 4), "predicted": round(float(y_pred[i]), 4)} for i in indices
        ]
        metrics["predictions_sample"] = preds_sample

        # Residuals Histogram (20 bins)
        residuals = y_test - y_pred
        counts, bin_edges = np.histogram(residuals, bins=20)
        metrics["residual_histogram"] = {
            "counts": [int(c) for c in counts],
            "bin_edges": [round(float(b), 4) for b in bin_edges],
        }

        metrics.update(
            {
                "r2": round(r2, 4),
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "median_ae": round(med_ae, 4),
            }
        )

        summary = {
            "r2": round(r2, 4),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
        }

    return metrics, summary

"""Feature importance computation and explainability."""

from typing import Any

import numpy as np
from sklearn.inspection import permutation_importance


def compute_feature_importance(
    pipeline: Any,
    X_test: Any,
    y_test: np.ndarray,
    original_feature_columns: list[str],
) -> dict[str, Any]:
    """Compute normalized feature importance (top 20) and aggregations by original column."""
    preprocessor = pipeline.named_steps["pre"]
    estimator = pipeline.named_steps["model"]

    # 1. Get feature names out of the ColumnTransformer
    try:
        feature_names = list(preprocessor.get_feature_names_out())
    except Exception:
        # Fallback to generic names if get_feature_names_out is not available
        n_features = X_test.shape[1] if hasattr(X_test, "shape") else len(original_feature_columns)
        feature_names = [f"feature_{i}" for i in range(n_features)]

    importances = None

    # 2. Tree-based models: feature_importances_
    if hasattr(estimator, "feature_importances_"):
        raw_imp = estimator.feature_importances_
        if raw_imp is not None and len(raw_imp) == len(feature_names):
            importances = np.array(raw_imp, dtype=float)

    # 3. Linear models: abs(coef_)
    elif hasattr(estimator, "coef_"):
        coef = estimator.coef_
        if coef is not None:
            # For multiclass, take mean across classes
            importances = np.mean(np.abs(coef), axis=0) if coef.ndim > 1 else np.abs(coef)

    # 4. Fallback: permutation_importance (e.g., for kNN)
    if importances is None or np.all(importances == 0):
        try:
            n_samples = min(2000, len(y_test))
            X_sample = X_test.iloc[:n_samples] if hasattr(X_test, "iloc") else X_test[:n_samples]
            y_sample = y_test[:n_samples]

            res = permutation_importance(
                pipeline,
                X_sample,
                y_sample,
                n_repeats=3,
                random_state=42,
            )
            raw_imp = res.importances_mean
            raw_imp[raw_imp < 0] = 0.0
            importances = raw_imp
        except Exception:
            importances = np.ones(len(feature_names))

    # Normalize to sum to 1.0
    total = np.sum(importances)
    norm_importances = importances / total if total > 0 else np.ones(len(feature_names)) / max(1, len(feature_names))

    # Combine names and scores
    all_features = [
        {"feature": name, "importance": round(float(imp), 4)}
        for name, imp in zip(feature_names, norm_importances, strict=False)
    ]
    # Sort descending
    all_features.sort(key=lambda x: x["importance"], reverse=True)
    top_20 = all_features[:20]

    # 5. Aggregate by original column
    aggregated: dict[str, float] = {col: 0.0 for col in original_feature_columns}
    for item in all_features:
        feat_name = item["feature"]
        score = item["importance"]
        matched = False
        # Match feature name to original column (e.g. cat__geography_France -> geography)
        for orig in original_feature_columns:
            if orig in feat_name:
                aggregated[orig] += score
                matched = True
                break
        if not matched:
            aggregated.setdefault("other", 0.0)
            aggregated["other"] += score

    agg_list = [{"column": col, "importance": round(score, 4)} for col, score in aggregated.items()]
    agg_list.sort(key=lambda x: x["importance"], reverse=True)

    return {
        "top_features": top_20,
        "aggregated_by_original_column": agg_list,
    }

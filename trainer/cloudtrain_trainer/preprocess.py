"""Feature preprocessing, ColumnTransformer construction, and column exclusion."""

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

from cloudtrain_trainer.data_loader import DataValidationError


def is_boolean_series(s: pd.Series) -> bool:
    """Check if series consists strictly of boolean-like values."""
    if pd.api.types.is_bool_dtype(s):
        return True
    non_null = s.dropna().astype(str).str.strip().str.lower().unique()
    bool_values = {"true", "false", "1", "0", "yes", "no", "t", "f", "y", "n"}
    return len(non_null) <= 2 and set(non_null).issubset(bool_values)


def is_datetime_series(s: pd.Series) -> bool:
    """Check if series can be parsed as datetimes for >= 90% non-null values."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if not (pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)):
        return False
    sample = s.dropna().head(100)
    if len(sample) == 0:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce")
        valid_ratio = parsed.notna().sum() / len(sample)
        return valid_ratio >= 0.9
    except Exception:
        return False


def build_preprocessor(
    X: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[ColumnTransformer, pd.DataFrame, dict[str, Any]]:
    """Analyze features, exclude unviable columns, expand datetimes, and construct ColumnTransformer.

    Returns (transformer, X_transformed, report).
    """
    prep_cfg = config.get("preprocessing", {})
    numeric_impute = prep_cfg.get("numeric_impute", "median")
    categorical_impute = prep_cfg.get("categorical_impute", "most_frequent")
    scale_numeric = prep_cfg.get("scale_numeric", True)
    max_categories = prep_cfg.get("max_categories", 50)
    drop_id_like = prep_cfg.get("drop_id_like", True)

    n_rows = len(X)
    X_work = X.copy()

    excluded_columns: dict[str, str] = {}
    datetime_columns_expanded: list[str] = []

    # 1. Expand Datetime Columns
    for col in list(X_work.columns):
        series = X_work[col]
        if is_datetime_series(series):
            parsed_dt = pd.to_datetime(series, errors="coerce")
            prefix = f"{col}_"
            X_work[f"{prefix}year"] = parsed_dt.dt.year.fillna(2000).astype(float)
            X_work[f"{prefix}month"] = parsed_dt.dt.month.fillna(1).astype(float)
            X_work[f"{prefix}day"] = parsed_dt.dt.day.fillna(1).astype(float)
            X_work[f"{prefix}dayofweek"] = parsed_dt.dt.dayofweek.fillna(0).astype(float)
            X_work[f"{prefix}hour"] = parsed_dt.dt.hour.fillna(0).astype(float)
            X_work = X_work.drop(columns=[col])
            datetime_columns_expanded.append(col)

    numeric_cols: list[str] = []
    boolean_cols: list[str] = []
    categorical_cols: list[str] = []

    # 2. Inspect each column for exclusion and type classification
    id_pattern = re.compile(r"(^id$|_id$|^id_|uuid|guid|index)", re.IGNORECASE)

    for col in X_work.columns:
        series = X_work[col]
        non_null_count = series.notna().sum()
        missing_count = n_rows - non_null_count
        missing_pct = (missing_count / n_rows) * 100.0

        # Check > 50% missing
        if missing_pct > 50.0:
            excluded_columns[col] = f"Missing {missing_pct:.1f}% values (> 50% threshold)"
            continue

        unique_count = series.nunique()
        # Check constant
        if unique_count <= 1:
            excluded_columns[col] = "Constant column (≤ 1 unique value)"
            continue

        unique_ratio = unique_count / max(1, non_null_count)

        # Check boolean
        if is_boolean_series(series):
            boolean_cols.append(col)
            continue

        # Check numeric
        if pd.api.types.is_numeric_dtype(series):
            numeric_cols.append(col)
            continue

        # Text/string inspection
        str_series = series.dropna().astype(str)
        mean_len = str_series.str.len().mean() if len(str_series) > 0 else 0

        # Check id_like
        if drop_id_like and ((unique_ratio >= 0.95 and n_rows > 20) or (id_pattern.search(col) and unique_ratio > 0.5)):
            excluded_columns[col] = "Identified as identifier column (high cardinality/id pattern)"
            continue

        # Check text (high uniqueness and long average length)
        if unique_ratio > 0.5 and mean_len > 30:
            excluded_columns[col] = f"Free text column (mean length {mean_len:.1f} > 30)"
            continue

        # Check max_categories
        if unique_count > max_categories:
            excluded_columns[col] = f"High cardinality categorical ({unique_count} > {max_categories} max_categories)"
            continue

        categorical_cols.append(col)

    # Convert boolean columns to 0/1 numeric
    for col in boolean_cols:

        def _to_bool_num(val: Any) -> float:
            if pd.isna(val):
                return np.nan
            s_val = str(val).strip().lower()
            return 1.0 if s_val in {"true", "1", "yes", "t", "y"} else 0.0

        X_work[col] = X_work[col].map(_to_bool_num)
        numeric_cols.append(col)

    total_kept_cols = numeric_cols + categorical_cols
    if not total_kept_cols:
        raise DataValidationError(
            "NO_USABLE_FEATURES",
            f"All features were excluded during preprocessing ({list(excluded_columns.keys())}). No usable features remain.",
        )

    # 3. Build ColumnTransformer transformers
    transformers = []

    if numeric_cols:
        num_missing_rates = [(X_work[c].isna().sum() / n_rows) for c in numeric_cols]
        has_high_missing = any(rate > 0.05 for rate in num_missing_rates)

        num_steps = [
            (
                "imputer",
                SimpleImputer(
                    strategy=numeric_impute if numeric_impute != "zero" else "constant",
                    fill_value=0.0 if numeric_impute == "zero" else None,
                    add_indicator=has_high_missing,
                ),
            )
        ]
        if scale_numeric:
            num_steps.append(("scaler", StandardScaler()))

        transformers.append(("num", Pipeline(num_steps), numeric_cols))

    if categorical_cols:
        cat_impute_strategy = "most_frequent" if categorical_impute == "most_frequent" else "constant"
        cat_steps = [
            (
                "imputer",
                SimpleImputer(
                    strategy=cat_impute_strategy,
                    fill_value="missing" if cat_impute_strategy == "constant" else None,
                ),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    min_frequency=0.01,
                    sparse_output=False,
                ),
            ),
        ]
        transformers.append(("cat", Pipeline(cat_steps), categorical_cols))

    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")

    report = {
        "original_features_count": len(X.columns),
        "retained_features_count": len(total_kept_cols),
        "numeric_features": numeric_cols,
        "categorical_features": categorical_cols,
        "datetime_columns_expanded": datetime_columns_expanded,
        "excluded_columns": excluded_columns,
    }

    # Filter X_work to only the columns that will be passed through preprocessor
    X_retained = X_work[total_kept_cols].copy()
    return preprocessor, X_retained, report


def encode_target(y: pd.Series, task: str) -> tuple[np.ndarray, list[Any] | None]:
    """Encode the target variable.

    For classification: LabelEncoder returns integer array and class names.
    For regression: Returns float array and None.
    """
    if task == "classification":
        le = LabelEncoder()
        y_encoded = le.fit_transform(y.astype(str))
        classes = list(le.classes_)
        return y_encoded, classes
    else:
        return y.to_numpy(dtype=float), None

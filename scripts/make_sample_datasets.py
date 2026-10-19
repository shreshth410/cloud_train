#!/usr/bin/env python3
"""Generate small sample datasets (< 1MB) for testing CloudTrain."""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.datasets import load_diabetes, load_iris


def generate_iris(output_path: Path) -> None:
    """Generate the standard Iris classification dataset."""
    iris = load_iris(as_frame=True)
    df = iris.frame
    # Map target numbers to species names for realistic categorical target
    target_names = {0: "setosa", 1: "versicolor", 2: "virginica"}
    df["target"] = df["target"].map(target_names)
    df.to_csv(output_path, index=False)
    print(f"[OK] Generated {output_path} ({len(df)} rows, {len(df.columns)} cols)")


def generate_diabetes(output_path: Path) -> None:
    """Generate the standard Diabetes regression dataset."""
    diabetes = load_diabetes(as_frame=True)
    df = diabetes.frame
    df.to_csv(output_path, index=False)
    print(f"[OK] Generated {output_path} ({len(df)} rows, {len(df.columns)} cols)")


def generate_messy_churn(output_path: Path, n_rows: int = 500) -> None:
    """Generate a realistic messy tabular dataset testing all profiler heuristics.

    Includes:
    - Numeric features (age, credit_score, balance)
    - Categorical features (geography, gender)
    - Boolean features (has_cr_card, is_active_member)
    - Datetime feature (signup_date)
    - Constant column (currency = USD)
    - Id-like column (customer_id = CUST_...)
    - Missing values in some columns
    - Target: churn (0 or 1)
    """
    np.random.seed(42)

    customer_ids = [f"CUST_{i:05d}" for i in range(1, n_rows + 1)]
    credit_scores = np.random.randint(350, 850, size=n_rows).astype(float)
    geography = np.random.choice(
        ["France", "Germany", "Spain"], size=n_rows, p=[0.5, 0.25, 0.25]
    )
    gender = np.random.choice(["Male", "Female"], size=n_rows)
    age = np.random.randint(18, 75, size=n_rows).astype(float)
    tenure = np.random.randint(0, 10, size=n_rows)
    balance = np.random.uniform(0, 200000, size=n_rows)
    num_products = np.random.choice(
        [1, 2, 3, 4], size=n_rows, p=[0.5, 0.45, 0.04, 0.01]
    )
    has_cr_card = np.random.choice([True, False], size=n_rows)
    is_active_member = np.random.choice([1, 0], size=n_rows, p=[0.6, 0.4])
    estimated_salary = np.random.uniform(10000, 150000, size=n_rows)

    # Constant column
    currency = ["USD"] * n_rows

    # Datetime column
    base_date = pd.Timestamp("2023-01-01")
    random_days = pd.to_timedelta(np.random.randint(0, 365, size=n_rows), unit="D")
    signup_dates = [
        (base_date + day).strftime("%Y-%m-%d %H:%M:%S") for day in random_days
    ]

    # Target (binary classification)
    # Logit-like probability based on age and balance
    prob = 1 / (1 + np.exp(-(0.05 * (age - 40) + 0.00001 * balance - 0.5)))
    churn = (np.random.uniform(0, 1, size=n_rows) < prob).astype(int)

    df = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "credit_score": credit_scores,
            "geography": geography,
            "gender": gender,
            "age": age,
            "tenure": tenure,
            "balance": balance,
            "num_products": num_products,
            "has_cr_card": has_cr_card,
            "is_active_member": is_active_member,
            "estimated_salary": estimated_salary,
            "currency": currency,
            "signup_date": signup_dates,
            "churn": churn,
        }
    )

    # Introduce some realistic missing values
    # Age has ~8% missing
    age_nan_mask = np.random.rand(n_rows) < 0.08
    df.loc[age_nan_mask, "age"] = np.nan

    # Estimated salary has ~3% missing
    salary_nan_mask = np.random.rand(n_rows) < 0.03
    df.loc[salary_nan_mask, "estimated_salary"] = np.nan

    df.to_csv(output_path, index=False)
    print(f"[OK] Generated {output_path} ({len(df)} rows, {len(df.columns)} cols)")


def main() -> None:
    samples_dir = Path(__file__).resolve().parent.parent / "samples"
    samples_dir.mkdir(exist_ok=True)

    generate_iris(samples_dir / "iris.csv")
    generate_diabetes(samples_dir / "diabetes.csv")
    generate_messy_churn(samples_dir / "messy_churn.csv")


if __name__ == "__main__":
    main()

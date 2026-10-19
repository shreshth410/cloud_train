"""Training container entrypoint and pipeline execution orchestrator."""

import argparse
import io
import logging
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline

from cloudtrain_trainer.artifacts import save_and_upload_artifacts
from cloudtrain_trainer.config import load_job_config
from cloudtrain_trainer.data_loader import DataValidationError, load_dataset
from cloudtrain_trainer.evaluate import evaluate_model
from cloudtrain_trainer.explain import compute_feature_importance
from cloudtrain_trainer.models import create_estimator
from cloudtrain_trainer.preprocess import build_preprocessor, encode_target
from cloudtrain_trainer.status import StatusReporter


class TrainingTimeoutError(Exception):
    """Raised when training runtime exceeds MAX_RUNTIME_SECONDS."""

    pass


class TeeStream(io.StringIO):
    """Duplicates stream writes to both a memory buffer and original stream."""

    def __init__(self, original_stream):
        super().__init__()
        self.original_stream = original_stream

    def write(self, s):
        self.original_stream.write(s)
        return super().write(s)

    def flush(self):
        self.original_stream.flush()
        super().flush()


def run_pipeline(
    user_id: str,
    job_id: str,
    bucket_name: str | None = None,
    status_queue_url: str | None = None,
    s3_endpoint_url: str | None = None,
    sqs_endpoint_url: str | None = None,
    region: str | None = None,
    max_runtime_seconds: int | None = None,
    local_config_path: str | None = None,
    local_csv_path: str | None = None,
    local_output_dir: str | None = None,
) -> int:
    """Execute the end-to-end training pipeline."""
    reporter = StatusReporter(
        job_id=job_id,
        queue_url=status_queue_url,
        sqs_endpoint_url=sqs_endpoint_url,
        region=region,
    )

    # 1. BOOTSTRAP (5%)
    reporter.stage("BOOTSTRAP", 5, "Initializing container and environment.")

    # Timeout guard
    timeout_secs = max_runtime_seconds or int(os.getenv("MAX_RUNTIME_SECONDS", "1800"))
    timeout_timer: threading.Timer | None = None

    def _timeout_handler():
        reporter.fail("TIMEOUT", f"Training exceeded maximum allowed runtime ({timeout_secs}s).")
        raise TrainingTimeoutError(f"Training runtime exceeded {timeout_secs} seconds.")

    timeout_timer = threading.Timer(timeout_secs, _timeout_handler)
    timeout_timer.daemon = True
    timeout_timer.start()

    try:
        # 2. DOWNLOADING (10%)
        reporter.stage("DOWNLOADING", 10, "Downloading configuration and dataset.")
        config = load_job_config(
            user_id=user_id,
            job_id=job_id,
            bucket_name=bucket_name,
            s3_endpoint_url=s3_endpoint_url,
            region=region,
            local_config_path=local_config_path,
        )

        # 3. VALIDATING (15%)
        reporter.stage("VALIDATING", 15, "Validating dataset dimensions, target column, and types.")
        X_raw, y_raw, resolved_task = load_dataset(
            config=config,
            bucket_name=bucket_name,
            s3_endpoint_url=s3_endpoint_url,
            region=region,
            local_csv_path=local_csv_path,
        )
        config["task"] = resolved_task

        # 4. PREPROCESSING (25%)
        reporter.stage("PREPROCESSING", 25, "Building transformers and preprocessing features.")
        preprocessor, X_clean, prep_report = build_preprocessor(X_raw, config)
        y_clean, label_classes = encode_target(y_raw, resolved_task)
        n_classes = len(label_classes) if label_classes else None

        # 5. TRAINING (40% -> 75%)
        reporter.stage("TRAINING", 40, "Preparing train/test split and estimator.")
        split_cfg = config.get("split", {})
        test_size = split_cfg.get("test_size", 0.2)
        random_state = split_cfg.get("random_state", 42)
        stratify_flag = split_cfg.get("stratify", True)

        # Stratify if classification and each class has at least 2 samples
        stratify_target = None
        if resolved_task == "classification" and stratify_flag:
            class_counts = np.bincount(y_clean)
            if np.all(class_counts >= 2):
                stratify_target = y_clean

        X_train, X_test, y_train, y_test = train_test_split(
            X_clean,
            y_clean,
            test_size=test_size,
            stratify=stratify_target,
            random_state=random_state,
        )

        estimator = create_estimator(
            model_cfg=config["model"],
            task=resolved_task,
            n_classes=n_classes,
            random_state=random_state,
        )
        pipeline = Pipeline([("pre", preprocessor), ("model", estimator)])

        # Cross validation if requested (folds >= 3)
        cv_cfg = config.get("cross_validation", {})
        cv_folds = cv_cfg.get("folds", 0)
        cv_scores: dict[str, Any] | None = None

        if cv_folds >= 3:
            reporter.stage("TRAINING", 45, f"Running {cv_folds}-fold cross validation.")
            if resolved_task == "classification":
                cv_splitter = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
                scoring = ["accuracy", "f1_weighted"]
            else:
                cv_splitter = KFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
                scoring = ["r2", "neg_mean_absolute_error"]

            cv_results = cross_validate(
                pipeline,
                X_train,
                y_train,
                cv=cv_splitter,
                scoring=scoring,
                n_jobs=-1,
            )

            cv_scores = {}
            for sc in scoring:
                key = f"test_{sc}"
                if key in cv_results:
                    vals = cv_results[key]
                    cv_scores[sc] = {
                        "mean": round(float(np.mean(vals)), 4),
                        "std": round(float(np.std(vals)), 4),
                    }
            reporter.stage("TRAINING", 65, "Completed cross validation.")

        reporter.stage("TRAINING", 70, f"Fitting final pipeline ({config['model']['id']}).")
        start_fit = time.time()
        pipeline.fit(X_train, y_train)
        fit_seconds = time.time() - start_fit

        # 6. EVALUATING (80%)
        reporter.stage("EVALUATING", 80, "Evaluating model on held-out test split.")
        full_metrics, headline_summary = evaluate_model(
            pipeline=pipeline,
            X_train=X_train,
            X_test=X_test,
            y_train=y_train,
            y_test=y_test,
            task=resolved_task,
            label_classes=label_classes,
            fit_seconds=fit_seconds,
            cv_scores=cv_scores,
        )
        reporter.metrics("EVALUATING", 85, headline_summary, "Headline metrics calculated.")

        # 7. EXPLAINING (88%)
        reporter.stage("EXPLAINING", 88, "Computing feature importances and explainability.")
        feature_importance = compute_feature_importance(
            pipeline=pipeline,
            X_test=X_test,
            y_test=y_test,
            original_feature_columns=list(X_clean.columns),
        )

        # 8. UPLOADING (95%)
        reporter.stage("UPLOADING", 95, "Packaging and uploading artifacts.")
        out_dir = Path(local_output_dir or f"/tmp/artifacts/{job_id}")
        save_and_upload_artifacts(
            output_dir=out_dir,
            pipeline=pipeline,
            config=config,
            metrics=full_metrics,
            feature_importance=feature_importance,
            preprocessing_report=prep_report,
            label_classes=label_classes,
            feature_columns=list(X_clean.columns),
            task=resolved_task,
            bucket_name=bucket_name,
            user_id=user_id,
            job_id=job_id,
            s3_endpoint_url=s3_endpoint_url,
            region=region,
        )

        # 9. DONE (100%)
        reporter.succeed(summary=headline_summary)
        return 0

    except DataValidationError as exc:
        reporter.fail(exc.code, exc.message)
        return 1
    except TrainingTimeoutError as exc:
        reporter.fail("TIMEOUT", str(exc))
        return 1
    except MemoryError:
        reporter.fail(
            "OUT_OF_MEMORY",
            "Training process exceeded available RAM. Please re-run the job with a larger compute size.",
        )
        return 1
    except ValueError as exc:
        msg = str(exc)
        if "ARTIFACT_TOO_LARGE" in msg:
            reporter.fail("ARTIFACT_TOO_LARGE", msg)
        else:
            reporter.fail("CONFIG_INVALID", msg)
        return 1
    except Exception as exc:
        print(f"Internal error trace:\n{traceback.format_exc()}", file=sys.stderr)
        reporter.fail("INTERNAL_ERROR", f"An unexpected training error occurred: {exc}")
        return 1
    finally:
        if timeout_timer:
            timeout_timer.cancel()


def main():
    """Main CLI entrypoint teeing stdout/stderr to logs.txt."""
    parser = argparse.ArgumentParser(description="CloudTrain Model Trainer")
    parser.add_argument("--job-id", default=os.getenv("JOB_ID", "local-job"))
    parser.add_argument("--user-id", default=os.getenv("USER_ID", "local-user"))
    parser.add_argument("--data-bucket", default=os.getenv("DATA_BUCKET"))
    parser.add_argument("--status-queue-url", default=os.getenv("STATUS_QUEUE_URL"))
    parser.add_argument("--s3-endpoint-url", default=os.getenv("S3_ENDPOINT_URL"))
    parser.add_argument("--sqs-endpoint-url", default=os.getenv("SQS_ENDPOINT_URL"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-south-1"))
    parser.add_argument("--max-runtime-seconds", type=int, default=os.getenv("MAX_RUNTIME_SECONDS"))
    parser.add_argument("--config", default=None, help="Local config.json path")
    parser.add_argument("--data", default=None, help="Local CSV path")
    parser.add_argument("--output-dir", default=None, help="Local artifacts directory")
    args = parser.parse_args()

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    exit_code = run_pipeline(
        user_id=args.user_id,
        job_id=args.job_id,
        bucket_name=args.data_bucket,
        status_queue_url=args.status_queue_url,
        s3_endpoint_url=args.s3_endpoint_url,
        sqs_endpoint_url=args.sqs_endpoint_url,
        region=args.region,
        max_runtime_seconds=args.max_runtime_seconds,
        local_config_path=args.config,
        local_csv_path=args.data,
        local_output_dir=args.output_dir,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

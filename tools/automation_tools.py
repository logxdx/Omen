from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from agents import function_tool

try:  # Optional heavy imports guarded for runtime
    import pandas as pd
except ImportError:  # pragma: no cover - runtime failure will be surfaced
    pd = None  # type: ignore

from tools.utils.dataset_utils import (
    dataframe_column_partitions,
    ensure_pandas_available,
    load_dataframe,
    resolve_dataset_path,
    sample_if_needed,
)
from tools.utils.filesystem import SANDBOX_PATH, AccessDeniedError
from .data_tools import (
    dataset_overview,
    dataset_quality_report,
    dataset_correlation_report,
)

if TYPE_CHECKING:  # pragma: no cover
    from pandas import DataFrame

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    r2_score,
    mean_absolute_error,
    mean_squared_error,
)


def _safe_artifact_dir(custom_subdir: str | None) -> Path:
    base_dir = SANDBOX_PATH / "analysis_outputs"
    base_dir.mkdir(parents=True, exist_ok=True)

    if custom_subdir:
        candidate = (SANDBOX_PATH / custom_subdir).resolve()
        if not str(candidate).startswith(str(SANDBOX_PATH.resolve())):
            raise AccessDeniedError("Artifact directory must live inside ./root")
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifact_dir = base_dir / f"auto_run_{timestamp}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _build_preprocessor(df: "DataFrame") -> tuple[ColumnTransformer, list[str], list[str]]:
    numeric_cols, categorical_cols = dataframe_column_partitions(df)
    transformers = []

    if numeric_cols:
        transformers.append(
            (
                "num",
                Pipeline(
                    steps=[
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric_cols,
            )
        )

    if categorical_cols:
        transformers.append(
            (
                "cat",
                Pipeline(
                    steps=[
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=False,
                                max_categories=60,
                            ),
                        ),
                    ]
                ),
                categorical_cols,
            )
        )

    if not transformers:
        raise ValueError("No usable feature columns after excluding the target")

    return ColumnTransformer(transformers), numeric_cols, categorical_cols


def _infer_problem_type(y: "pd.Series", override: Literal["auto", "classification", "regression"]) -> str:
    if override in {"classification", "regression"}:
        return override

    unique_values = y.nunique(dropna=True)
    if pd.api.types.is_numeric_dtype(y):
        return "classification" if unique_values <= 15 else "regression"
    return "classification"


def _classification_metrics(y_true, y_pred, y_proba=None) -> dict:
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_weighted": precision_score(y_true, y_pred, average="weighted", zero_division=0),
        "recall_weighted": recall_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }
    unique_classes = pd.Series(y_true).nunique(dropna=True)
    if unique_classes == 2 and y_proba is not None:
        try:
            metrics["roc_auc"] = roc_auc_score(y_true, y_proba[:, 1])
        except Exception:
            pass
    return metrics


def _regression_metrics(y_true, y_pred) -> dict:
    return {
        "r2": r2_score(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": mean_squared_error(y_true, y_pred, squared=False),
    }


def _model_configs(problem_type: str, random_state: int):
    if problem_type == "classification":
        return [
            ("LogisticRegression", LogisticRegression(max_iter=1000)),
            (
                "RandomForestClassifier",
                RandomForestClassifier(n_estimators=300, random_state=random_state),
            ),
        ]
    return [
        ("LinearRegression", LinearRegression()),
        (
            "RandomForestRegressor",
            RandomForestRegressor(n_estimators=300, random_state=random_state),
        ),
    ]


def _serialize_metrics(metrics: dict) -> str:
    return json.dumps(metrics, indent=2, default=lambda o: float(o))


@function_tool
def automated_eda_report(relative_path: str, target_column: str | None = None, sample_rows: int = 5000) -> str:
    """Compose overview, quality, and correlation reports in a single call."""

    sections = [
        dataset_overview(relative_path, sample_rows=min(sample_rows, 25)),
        dataset_quality_report(relative_path, sample_rows=sample_rows),
        dataset_correlation_report(relative_path, target_column=target_column, sample_rows=sample_rows),
    ]
    return "\n\n---\n\n".join(sections)


@function_tool
def automated_modeling_workflow(
    relative_path: str,
    target_column: str,
    problem_type: Literal["auto", "classification", "regression"] = "auto",
    test_size: float = 0.2,
    random_state: int = 42,
    max_rows: int | None = 20000,
    artifact_subdir: str | None = None,
) -> str:
    """Train + evaluate baseline models with automatic preprocessing and artifact logging."""

    try:
        ensure_pandas_available()
        path = resolve_dataset_path(relative_path)
        df = load_dataframe(path)
    except Exception as exc:  # pragma: no cover
        return f"automated_modeling_workflow failed: {exc}"

    if target_column not in df.columns:
        return f"automated_modeling_workflow failed: target column '{target_column}' missing"

    df = df.dropna(subset=[target_column])
    df = sample_if_needed(df, max_rows=max_rows, random_state=random_state)

    y = df[target_column]
    X = df.drop(columns=[target_column])
    if X.empty:
        return "automated_modeling_workflow failed: no feature columns remain after dropping the target"

    inferred_problem_type = _infer_problem_type(y, problem_type)

    try:
        preprocessor, numeric_cols, categorical_cols = _build_preprocessor(X)
    except ValueError as exc:
        return f"automated_modeling_workflow failed: {exc}"

    if not 0.05 <= test_size <= 0.4:
        return "automated_modeling_workflow failed: test_size should be between 0.05 and 0.4"

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if inferred_problem_type == "classification" else None,
    )

    models = _model_configs(inferred_problem_type, random_state)
    model_summaries = []

    for name, estimator in models:
        pipeline = Pipeline([
            ("preprocess", preprocessor),
            ("estimator", estimator),
        ])

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)

        metrics = (
            _classification_metrics(y_test, y_pred, pipeline.predict_proba(X_test) if hasattr(pipeline, "predict_proba") else None)
            if inferred_problem_type == "classification"
            else _regression_metrics(y_test, y_pred)
        )

        model_summaries.append({
            "model": name,
            "metrics": metrics,
        })

    artifact_dir = _safe_artifact_dir(artifact_subdir)
    artifact_payload = {
        "dataset": str(path.relative_to(SANDBOX_PATH)),
        "problem_type": inferred_problem_type,
        "target": target_column,
        "test_size": test_size,
        "rows_used": len(df),
        "models": model_summaries,
        "numeric_features": numeric_cols,
        "categorical_features": categorical_cols,
    }

    metrics_path = artifact_dir / "metrics.json"
    metrics_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")

    summary_lines = [
        "## AUTOMATED MODELING WORKFLOW",
        f"Dataset: {relative_path}",
        f"Target: {target_column}",
        f"Problem Type: {inferred_problem_type}",
        f"Rows Used: {len(df)} (after dropna/sample)",
        f"Test Size: {test_size}",
        f"Artifacts: {metrics_path.relative_to(SANDBOX_PATH)}",
        "",
        "### Feature Space",
        f"Numeric ({len(numeric_cols)}): {', '.join(numeric_cols) or 'None'}",
        f"Categorical ({len(categorical_cols)}): {', '.join(categorical_cols) or 'None'}",
        "",
        "### Model Metrics",
    ]

    for summary in model_summaries:
        summary_lines.append(f"- {summary['model']}: {_serialize_metrics(summary['metrics'])}")

    return "\n".join(summary_lines)


AUTOMATION_TOOLS = [
    automated_eda_report,
    automated_modeling_workflow,
]

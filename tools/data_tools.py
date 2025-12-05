from __future__ import annotations

import math
from typing import Iterable, TYPE_CHECKING

from agents import function_tool

try:  # Optional dependency guard for compile time
    import pandas as pd
except ImportError:  # pragma: no cover - handled at runtime
    pd = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from pandas import DataFrame
else:  # Fallback type used only at runtime when pandas is absent
    DataFrame = object

from tools.utils.dataset_utils import (
    load_dataframe,
    resolve_dataset_path,
    human_readable_size,
)


def _format_dataframe(df: "DataFrame", max_rows: int = 10, max_cols: int = 12) -> str:
    if df.empty:
        return "(dataset sample returned 0 rows)"
    preview_rows = min(max_rows, len(df))
    with pd.option_context(  # type: ignore[attr-defined]
        "display.max_rows",
        preview_rows,
        "display.max_columns",
        max_cols,
        "display.width",
        120,
        "display.max_colwidth",
        120,
    ):
        return df.head(preview_rows).to_string(index=False)


def _format_mapping(mapping: dict[str, float | int]) -> str:
    lines = []
    for key, value in mapping.items():
        if isinstance(value, float):
            value = round(value, 4)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "(no data)"


def _format_table_from_series(series, top_n: int = 12) -> str:
    if series.empty:
        return "(no data)"
    limited = series.head(top_n)
    width = max(len(str(idx)) for idx in limited.index)
    rows = [f"{str(idx):<{width}} | {round(value, 4) if isinstance(value, float) else value}" for idx, value in limited.items()]
    return "\n".join(rows)


def _list_to_bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


@function_tool
def dataset_overview(relative_path: str, sample_rows: int = 5) -> str:
    """Quickly inspect a dataset: metadata, schema preview, and sample rows."""

    try:
        path = resolve_dataset_path(relative_path)
        df = load_dataframe(path, nrows=max(sample_rows, 10))
        file_size = human_readable_size(path.stat().st_size)
    except Exception as exc:  # pragma: no cover - run-time error string for agents
        return f"dataset_overview failed: {exc}"

    dtype_lines = _list_to_bullets(f"{col}: {dtype}" for col, dtype in df.dtypes.items())
    preview = _format_dataframe(df, max_rows=sample_rows)

    response = [
        "## DATASET OVERVIEW",
        f"Path: {relative_path}",
        f"Format: {path.suffix}",
        f"File Size: {file_size}",
        f"Rows Loaded: {len(df)} (sample)",
        f"Columns: {len(df.columns)}",
        "",
        "### Schema Preview",
        dtype_lines or "(no columns detected)",
        "",
        f"### Sample (up to {sample_rows} rows)",
        preview,
    ]
    return "\n".join(response)


@function_tool
def dataset_quality_report(relative_path: str, sample_rows: int = 5000) -> str:
    """Generate missing-value, cardinality, and summary stats snapshots."""

    try:
        path = resolve_dataset_path(relative_path)
        df = load_dataframe(path, nrows=sample_rows)
    except Exception as exc:
        return f"dataset_quality_report failed: {exc}"

    numeric_df = df.select_dtypes(include="number")
    categorical_df = df.select_dtypes(exclude="number")

    missing_counts = df.isna().sum().sort_values(ascending=False)
    missing_section = _format_table_from_series(missing_counts[missing_counts > 0])

    cardinality = df.nunique(dropna=True).sort_values(ascending=False)
    cardinality_section = _format_table_from_series(cardinality)

    summary_blocks = []
    if not numeric_df.empty:
        summary_blocks.append("### Numeric Summary (sample)")
        summary_blocks.append(_format_dataframe(numeric_df.describe().transpose(), max_rows=12))
    if not categorical_df.empty:
        summary_blocks.append("### Categorical Summary (top 12 columns)")
        summary_blocks.append(_format_dataframe(categorical_df.describe().transpose(), max_rows=12))

    response = [
        "## DATASET QUALITY REPORT",
        f"Path: {relative_path}",
        f"Rows Analyzed (sample limit {sample_rows}): {len(df)}",
        "",
        "### Missing Values (descending)",
        missing_section or "(no missing values detected)",
        "",
        "### Cardinality (unique counts)",
        cardinality_section or "(cardinality not available)",
        "",
    ]
    response.extend(summary_blocks or ["(No descriptive statistics available)"])
    return "\n".join(response)


@function_tool
def dataset_correlation_report(
    relative_path: str,
    target_column: str | None = None,
    sample_rows: int = 5000,
) -> str:
    """Compute correlation strengths to surface predictive signals quickly."""

    try:
        path = resolve_dataset_path(relative_path)
        df = load_dataframe(path, nrows=sample_rows)
    except Exception as exc:
        return f"dataset_correlation_report failed: {exc}"

    numeric_df = df.select_dtypes(include="number").dropna()
    if numeric_df.empty:
        return "dataset_correlation_report: No numeric columns available for correlation analysis."

    corr = numeric_df.corr(numeric_only=True).abs()
    response = [
        "## DATASET CORRELATION REPORT",
        f"Path: {relative_path}",
        f"Numeric columns analyzed: {len(numeric_df.columns)}",
        f"Rows used (after dropna): {len(numeric_df)}",
        "",
    ]

    if target_column and target_column in corr.columns:
        target_corr = corr[target_column].drop(target_column).sort_values(ascending=False)
        response.append(f"### Correlations vs target '{target_column}'")
        response.append(_format_table_from_series(target_corr))
    else:
        upper_pairs = []
        columns = list(corr.columns)
        for i in range(len(columns)):
            for j in range(i + 1, len(columns)):
                col_i = columns[i]
                col_j = columns[j]
                score = corr.iloc[i, j]
                if math.isnan(score):
                    continue
                upper_pairs.append(((col_i, col_j), score))
        upper_pairs.sort(key=lambda item: item[1], reverse=True)
        top_pairs = upper_pairs[:15]
        if not top_pairs:
            response.append("(No valid correlation pairs computed)")
        else:
            response.append("### Top correlation pairs (absolute values)")
            rows = [
                f"{a} ↔ {b}: {score:.4f}"
                for (a, b), score in top_pairs
            ]
            response.append("\n".join(rows))

    return "\n".join(response)


DATA_ANALYSIS_TOOLS = [
    dataset_overview,
    dataset_quality_report,
    dataset_correlation_report,
]

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

from tools.utils.filesystem import SANDBOX_PATH, AccessDeniedError

try:  # Optional dependency guard
    import pandas as pd
except ImportError:  # pragma: no cover - runtime error surface via helper
    pd = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from pandas import DataFrame
else:
    DataFrame = object


SUPPORTED_DATASET_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".txt",
    ".json",
    ".ndjson",
    ".parquet",
    ".pq",
    ".xlsx",
    ".xls",
}


def ensure_pandas_available() -> None:
    """Raise an informative error if pandas or its optional readers are missing."""

    if pd is None:  # type: ignore
        raise ImportError(
            "pandas is required for dataset tooling. Install pandas (plus pyarrow/openpyxl for Parquet/Excel) to continue."
        )


def resolve_dataset_path(relative_path: str) -> Path:
    """Resolve a dataset path relative to ./root, ensuring sandbox safety."""

    if not relative_path or not relative_path.strip():
        raise ValueError("Provide a dataset path relative to ./root")

    candidate = (SANDBOX_PATH / relative_path).resolve()
    sandbox = SANDBOX_PATH.resolve()
    if not str(candidate).startswith(str(sandbox)):
        raise AccessDeniedError("Access denied outside ./root sandbox")
    if not candidate.exists():
        raise FileNotFoundError(f"Dataset not found: {relative_path}")
    if not candidate.is_file():
        raise IsADirectoryError(f"Dataset path is a directory: {relative_path}")
    if candidate.suffix.lower() not in SUPPORTED_DATASET_EXTENSIONS:
        raise ValueError(
            f"Unsupported dataset format '{candidate.suffix}'. Supported extensions: {', '.join(sorted(SUPPORTED_DATASET_EXTENSIONS))}"
        )
    return candidate


def load_dataframe(path: Path, nrows: int | None = None):
    """Load a pandas DataFrame from a validated Path."""

    ensure_pandas_available()
    suffix = path.suffix.lower()
    read_kwargs = {"nrows": nrows} if nrows else {}

    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path, **read_kwargs)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", **read_kwargs)
    if suffix in {".json", ".ndjson"}:
        try:
            df = pd.read_json(path, lines=False)
        except ValueError:
            df = pd.read_json(path, lines=True)
        return df.head(nrows) if nrows else df
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **read_kwargs)

    raise ValueError(f"Unsupported dataset format '{suffix}'")


def load_dataframe_from_relative_path(relative_path: str, nrows: int | None = None):
    """Convenience helper that resolves and loads a dataset in one call."""

    path = resolve_dataset_path(relative_path)
    return load_dataframe(path, nrows=nrows)


def human_readable_size(num_bytes: int) -> str:
    """Return a compact human-readable string for byte counts."""

    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = min(int(math.log(num_bytes, 1024)), len(units) - 1)
    return f"{num_bytes / (1024 ** idx):.2f} {units[idx]}"


def dataframe_column_partitions(df: "DataFrame") -> tuple[list[str], list[str]]:
    """Split dataframe columns into numeric vs categorical lists."""

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [col for col in df.columns if col not in numeric_cols]
    return numeric_cols, categorical_cols


def sample_if_needed(df: "DataFrame", max_rows: int | None, random_state: int = 42):
    """Down-sample a dataframe if it exceeds max_rows."""

    if max_rows is None or len(df) <= max_rows:
        return df
    return df.sample(max_rows, random_state=random_state)


def dataset_metadata(path: Path, df: "DataFrame") -> dict:
    """Produce a minimal metadata dict for reporting."""

    return {
        "path": str(path.relative_to(SANDBOX_PATH)),
        "format": path.suffix,
        "rows": len(df),
        "columns": len(df.columns),
        "file_size": human_readable_size(os.path.getsize(path)),
    }

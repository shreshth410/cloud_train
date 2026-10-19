"""Dataset profiling and tabular heuristics implementation.

Computes column types, statistics, missing values, warnings, and preview
per Section 7.4 of SPEC.md.
"""

import contextlib
import csv
import io
import re
from datetime import datetime
from typing import Any

BOOLEAN_TOKENS = {"true", "false", "yes", "no", "0", "1", "t", "f", "y", "n"}

DATETIME_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
]

ID_NAME_REGEX = re.compile(r"(^id$|_id$|^id_|uuid|guid|index)", re.IGNORECASE)


def detect_encoding_and_delimiter(raw_bytes: bytes) -> tuple[str, str, str]:
    """Detect encoding and delimiter for a CSV byte buffer.

    Returns (text_content, encoding, delimiter).
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            # Sniff delimiter on sample
            sample = text[:16384]
            delimiter = ","
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=",;\t|")
                delimiter = dialect.delimiter
            except Exception:
                # Count candidate occurrences in first few lines
                first_lines = sample.splitlines()[:5]
                best_delim = ","
                best_count = 0
                for d in (",", ";", "\t", "|"):
                    counts = [line.count(d) for line in first_lines if line.strip()]
                    if counts and all(c > 0 and c == counts[0] for c in counts) and counts[0] > best_count:
                        best_delim = d
                        best_count = counts[0]
                delimiter = best_delim
            return text, enc, delimiter
        except UnicodeDecodeError:
            continue

    raise ValueError("Could not decode file as UTF-8 or Latin-1.")


def is_float(val: str) -> bool:
    """Check if string parses as float."""
    try:
        float(val)
        return True
    except ValueError:
        return False


def is_datetime(val: str) -> bool:
    """Check if string parses with known datetime formats or ISO format."""
    val = val.strip()
    if not val:
        return False
    try:
        datetime.fromisoformat(val)
        return True
    except Exception:
        pass
    for fmt in DATETIME_FORMATS:
        try:
            datetime.strptime(val, fmt)
            return True
        except ValueError:
            pass
    return False


def infer_column_dtype(
    col_name: str,
    values: list[str],
    total_row_count: int,
) -> str:
    """Infer column data type based on SPEC Section 7.4 heuristics."""
    non_empty = [v.strip() for v in values if v.strip() != ""]
    if not non_empty:
        return "constant"

    unique_vals = set(non_empty)
    unique_count = len(unique_vals)

    # 1. Constant: exactly one distinct non-empty value
    if unique_count == 1:
        return "constant"

    # 2. Boolean: values in token set with <= 2 distinct
    if unique_count <= 2 and all(v.lower() in BOOLEAN_TOKENS for v in unique_vals):
        return "boolean"

    # 3. Numeric: >= 95% of non-empty parse as float
    numeric_matches = sum(1 for v in non_empty if is_float(v))
    if numeric_matches / len(non_empty) >= 0.95:
        return "numeric"

    # 4. Datetime: >= 95% parse as datetime
    dt_matches = sum(1 for v in non_empty if is_datetime(v))
    if dt_matches / len(non_empty) >= 0.95:
        return "datetime"

    unique_ratio = unique_count / len(non_empty)
    mean_length = sum(len(v) for v in non_empty) / len(non_empty)

    # 5. Text: string column with unique ratio > 0.5 AND mean length > 30
    if unique_ratio > 0.5 and mean_length > 30:
        return "text"

    # 6. ID-like:
    # non-float column with unique ratio >= 0.95 and > 20 rows,
    # or name matches regex with high uniqueness (> 0.8)
    if total_row_count > 20 and unique_ratio >= 0.95:
        return "id_like"
    if ID_NAME_REGEX.search(col_name) and unique_ratio > 0.8:
        return "id_like"

    # 7. Categorical fallback
    return "categorical"


def profile_csv_content(csv_bytes: bytes) -> tuple[dict[str, Any] | None, list[str]]:
    """Profile CSV byte content according to SPEC 7.4.

    Returns (profile_dict, validation_errors).
    """
    errors: list[str] = []

    if not csv_bytes or len(csv_bytes.strip()) == 0:
        return None, ["Dataset file is empty."]

    try:
        text, encoding, delimiter = detect_encoding_and_delimiter(csv_bytes)
    except Exception as e:
        return None, [f"Decoding failed: {e}"]

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader, None)
    except Exception as e:
        return None, [f"Failed to parse CSV header: {e}"]

    if not header:
        return None, ["Dataset file contains no header row."]

    # Check columns count
    col_count = len(header)
    if col_count > 500:
        return None, [f"Dataset exceeds maximum allowed columns (500). Found {col_count}."]

    # Check column names: duplicate or blank
    cleaned_header = [c.strip() for c in header]
    if any(c == "" for c in cleaned_header):
        errors.append("Dataset header contains blank column name(s).")

    seen_cols = set()
    dup_cols = set()
    for c in cleaned_header:
        if c in seen_cols:
            dup_cols.add(c)
        seen_cols.add(c)
    if dup_cols:
        errors.append(f"Duplicate column names detected: {', '.join(sorted(dup_cols))}.")

    if errors:
        return None, errors

    # Collect rows
    rows: list[list[str]] = []
    for r in reader:
        if not r or all(c.strip() == "" for c in r):
            continue  # skip completely blank rows
        # Pad or truncate row to header length
        if len(r) < col_count:
            r = r + [""] * (col_count - len(r))
        elif len(r) > col_count:
            r = r[:col_count]
        rows.append(r)

    total_rows = len(rows)
    if total_rows < 20:
        return None, [f"Dataset has fewer than 20 data rows (found {total_rows}). Minimum required is 20."]
    if total_rows > 1_000_000:
        return None, [f"Dataset exceeds maximum allowed rows (1,000,000). Found {total_rows}."]

    # First 10,000 rows for heuristic inference
    sample_rows = rows[:10000]

    columns_info: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, col_name in enumerate(cleaned_header):
        all_vals = [r[idx].strip() for r in rows]
        sample_vals = [r[idx].strip() for r in sample_rows]

        non_empty_all = [v for v in all_vals if v != ""]
        missing_count = total_rows - len(non_empty_all)
        missing_pct = round((missing_count / total_rows) * 100, 2)

        unique_set = set(non_empty_all)
        unique_count = len(unique_set)

        dtype = infer_column_dtype(col_name, sample_vals, total_rows)

        col_dict: dict[str, Any] = {
            "name": col_name,
            "dtype": dtype,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "unique_count": unique_count,
            "unique_capped": False,
            "sample_values": list(unique_set)[:3],
        }

        # Numeric stats
        if dtype == "numeric" and non_empty_all:
            float_vals = []
            for v in non_empty_all:
                with contextlib.suppress(ValueError):
                    float_vals.append(float(v))
            if float_vals:
                col_dict["stats"] = {
                    "min": round(min(float_vals), 4),
                    "max": round(max(float_vals), 4),
                    "mean": round(sum(float_vals) / len(float_vals), 4),
                }

        columns_info.append(col_dict)

        # Warnings
        if dtype == "id_like":
            warnings.append(f"Column '{col_name}' looks like an identifier and will be excluded by default.")
        elif dtype == "constant":
            warnings.append(f"Column '{col_name}' has only one unique value and will be excluded.")
        elif dtype == "text":
            warnings.append(f"Column '{col_name}' appears to be free text and will be excluded by default.")
        elif missing_pct > 50:
            warnings.append(f"Column '{col_name}' has {missing_pct}% missing values and may be dropped.")

    preview_rows = rows[:5]

    profile: dict[str, Any] = {
        "row_count": total_rows,
        "column_count": col_count,
        "delimiter": delimiter,
        "encoding": encoding,
        "columns": columns_info,
        "preview_rows": preview_rows,
        "warnings": warnings,
    }

    return profile, []

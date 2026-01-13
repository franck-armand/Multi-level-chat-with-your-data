from __future__ import annotations

from typing import Optional
import pandas as pd


class ChartError(RuntimeError):
    pass


def _require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ChartError(f"Missing required columns for chart: {missing}. Available: {list(df.columns)}")


def make_chart_payload(
    df: pd.DataFrame,
    chart_type: str,
    x: str,
    y: str,
    title: Optional[str] = None,
):
    """
    Returns a normalized payload the UI can render.
    We don't render here yet (that stays in Streamlit layer),
    but we make the transformation deterministic.
    """
    chart_type = (chart_type or "").lower().strip()
    if chart_type not in {"bar", "hist", "pie"}:
        raise ChartError(f"Unsupported chart_type: {chart_type}")

    _require_columns(df, [x, y])

    # Clean and coerce numeric y
    plot_df = df[[x, y]].copy()
    plot_df[y] = pd.to_numeric(plot_df[y], errors="coerce")
    plot_df = plot_df.dropna(subset=[y])

    if chart_type == "hist":
        # histogram expects y as numeric values (binning done in UI or here later)
        return {
            "type": "hist",
            "title": title or f"Histogram of {y}",
            "x": y,
            "data": plot_df[y].tolist(),
        }

    if chart_type == "pie":
        # pie expects categories + values
        # aggregate if repeated categories
        agg = plot_df.groupby(x, as_index=False)[y].sum()
        return {
            "type": "pie",
            "title": title or f"{y} by {x}",
            "labels": agg[x].astype(str).tolist(),
            "values": agg[y].tolist(),
        }

    # bar
    # If repeated categories, aggregate
    agg = plot_df.groupby(x, as_index=False)[y].sum().sort_values(by=y, ascending=False)
    return {
        "type": "bar",
        "title": title or f"{y} by {x}",
        "x": x,
        "y": y,
        "dataframe": agg,
    }

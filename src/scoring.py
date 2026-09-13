"""Bridge from the data contract to the FROZEN scorer's input schema (harness-owned).

src/scorer.py is frozen and expects the v0 frame shapes. This is the one place those
legacy column names are spelled outside the scorer itself; nothing dataset-specific
lives here.
"""

from __future__ import annotations

import pandas as pd

from .contract import Dataset
from .features import HORIZON


def scorer_frames(ds: Dataset, first_origin: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Contract tables -> the frame shapes the FROZEN scorer expects.

    scorer.series_weights joins (store_id, item_id, wm_yr_wk) -> sell_price over the 28
    days before each origin. We give it series_id as item_id, a constant store_id, a daily
    "week" key (the day ordinal), and the dataset's weight-price role per (series, day).
    For M5 this reproduces the weekly-price join exactly. Prices are restricted to the
    dates any fold's weight window can touch, to keep the merge small.
    """
    sales = ds.panel.rename(columns={"series_id": "id", "y": "sales"})
    sales = sales.assign(item_id=sales["id"], store_id="_")[["id", "item_id", "store_id", "date", "sales"]]
    calendar = pd.DataFrame({"date": ds.exog_date["date"]})
    calendar["wm_yr_wk"] = (calendar["date"] - pd.Timestamp("1970-01-01")).dt.days.astype("int64")
    wp = ds.roles["weight_price"]
    px = ds.exog_series[ds.exog_series["date"] >= first_origin - pd.Timedelta(days=HORIZON)]
    prices = pd.DataFrame({
        "store_id": "_",
        "item_id": px["series_id"].to_numpy(),
        "wm_yr_wk": (px["date"] - pd.Timestamp("1970-01-01")).dt.days.astype("int64").to_numpy(),
        "sell_price": px[wp].to_numpy(),
    })
    return sales, calendar, prices



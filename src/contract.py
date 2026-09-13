"""The data contract. Every model, feature builder, and harness module speaks this and
nothing dataset-specific; adapters (src/adapters/) translate a raw dataset into it.

A Dataset is four tables plus roles:

  panel        series_id, date, y            one row per series per day, no gaps, y >= 0
  series       series_id + static attributes  dataset-specific column names
  exog_date    date + known-in-advance regressors that vary only by date (calendar flags,
               event flags)
  exog_series  series_id, date + known-in-advance regressors that vary by series and date
               (price)
  roles        which columns play which part:
                 calendar_flags  list of exog_date columns used as binary/int flags, in
                                 feature order
                 price           the exog_series column used as the price feature
                 weight_price    the exog_series column the scorer uses for dollar weights
                                 (normally the same as price)
                 categoricals    list of series columns used as categorical features, in
                                 feature order

"Known in advance" is the adapter's claim, made in its docstring, that every exog value at
date d is knowable at any as-of date <= d. The contract cannot check that; the adversary can.

validate() checks structure only: no missing days, no negative y, no target-like column in
exog, roles that resolve, ids that agree across tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

REQUIRED_ROLES = ("calendar_flags", "price", "weight_price", "categoricals")


@dataclass
class Dataset:
    dataset_id: str
    panel: pd.DataFrame
    series: pd.DataFrame
    exog_date: pd.DataFrame
    exog_series: pd.DataFrame
    roles: dict = field(default_factory=dict)
    horizon: int = 28
    notes: str = ""

    @property
    def last_date(self) -> pd.Timestamp:
        return pd.Timestamp(self.panel["date"].max())


class ContractError(ValueError):
    pass


def validate(ds: Dataset) -> None:
    p, s, xd, xs = ds.panel, ds.series, ds.exog_date, ds.exog_series
    for name, frame, cols in (
        ("panel", p, ("series_id", "date", "y")),
        ("series", s, ("series_id",)),
        ("exog_date", xd, ("date",)),
        ("exog_series", xs, ("series_id", "date")),
    ):
        missing = [c for c in cols if c not in frame.columns]
        if missing:
            raise ContractError(f"{name} lacks required column(s) {missing}")
    for name, frame in (("panel", p), ("exog_date", xd), ("exog_series", xs)):
        if not pd.api.types.is_datetime64_any_dtype(frame["date"]):
            raise ContractError(f"{name}.date must be datetime64")

    if (p["y"] < 0).any():
        raise ContractError("panel.y has negative values")
    if p.duplicated(["series_id", "date"]).any():
        raise ContractError("panel has duplicate (series_id, date) rows")
    n_series, n_days = p["series_id"].nunique(), p["date"].nunique()
    if len(p) != n_series * n_days:
        raise ContractError(
            f"panel is not a full grid: {len(p):,} rows for {n_series} series x {n_days} days"
        )
    days = pd.DatetimeIndex(sorted(p["date"].unique()))
    gaps = (days[1:] - days[:-1]) != pd.Timedelta(days=1)
    if gaps.any():
        raise ContractError(f"panel has {int(gaps.sum())} gap(s) in its daily calendar")

    ids = set(p["series_id"].unique())
    if set(s["series_id"]) != ids:
        raise ContractError("series table ids differ from panel ids")
    if s["series_id"].duplicated().any():
        raise ContractError("series table has duplicate ids")
    if not ids <= set(xs["series_id"].unique()) and len(xs):
        raise ContractError("exog_series lacks rows for some panel series")
    if xd["date"].duplicated().any():
        raise ContractError("exog_date has duplicate dates")
    if not set(days) <= set(xd["date"]):
        raise ContractError("exog_date does not cover every panel day")

    for frame, name in ((xd, "exog_date"), (xs, "exog_series")):
        bad = [c for c in frame.columns if c in ("y", "sales", "target", "actual")]
        if bad:
            raise ContractError(f"{name} contains target-like column(s) {bad}")

    roles = ds.roles
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        raise ContractError(f"roles lack {missing}")
    for c in roles["calendar_flags"]:
        if c not in xd.columns:
            raise ContractError(f"calendar flag role '{c}' is not an exog_date column")
    for r in ("price", "weight_price"):
        if roles[r] not in xs.columns:
            raise ContractError(f"{r} role '{roles[r]}' is not an exog_series column")
    for c in roles["categoricals"]:
        if c not in s.columns:
            raise ContractError(f"categorical role '{c}' is not a series column")

"""Synthetic M5-shaped fixture — NOT M5 data. Same schema and dimensions
(823 series x 1913 days), fake numbers. Lets the harness be validated end to end
without Kaggle credentials: writes data/raw/*.csv, then run `make data`.

Never use this for a scored run that gets reported as a result."""
import numpy as np, pandas as pd

rng = np.random.default_rng(7)
N_DAYS, N_ITEMS = 1913, 823
start = pd.Timestamp("2011-01-29")
dates = pd.date_range(start, periods=N_DAYS, freq="D")

wm_yr_wk = []
for i, d in enumerate(dates):
    wk = i // 7
    wm_yr_wk.append(11101 + (wk // 52) * 100 + (wk % 52))
cal = pd.DataFrame({
    "date": dates,
    "wm_yr_wk": wm_yr_wk,
    "weekday": dates.day_name(),
    "wday": ((dates.dayofweek + 2) % 7) + 1,
    "month": dates.month, "year": dates.year,
    "d": [f"d_{i+1}" for i in range(N_DAYS)],
})
ev = np.full(N_DAYS, None, dtype=object)
ev_idx = rng.choice(N_DAYS, size=160, replace=False)
ev[ev_idx] = "SomeEvent"
cal["event_name_1"] = ev
cal["event_type_1"] = np.where(pd.isna(cal["event_name_1"]), None, "National")
cal["event_name_2"] = None
cal["event_type_2"] = None
for st in ("CA", "TX", "WI"):
    cal[f"snap_{st}"] = ((dates.day <= 10)).astype(int)
cal.to_csv("data/raw/calendar.csv", index=False)

items = [f"FOODS_3_{i+1:03d}" for i in range(N_ITEMS)]
base = rng.gamma(1.2, 1.6, N_ITEMS)[:, None]
dow_eff = (1 + 0.35 * np.sin(np.arange(N_DAYS) * 2 * np.pi / 7))[None, :]
trend = np.linspace(0.85, 1.15, N_DAYS)[None, :]
snap = (1 + 0.12 * cal["snap_CA"].to_numpy())[None, :]
evb = (1 + 0.20 * (~pd.isna(cal["event_name_1"])).to_numpy())[None, :]
price = np.round(rng.uniform(1.0, 8.0, N_ITEMS)[:, None] * (1 - 0.12 * (rng.random((N_ITEMS, N_DAYS // 7 + 1)) < 0.10)), 2)
price_daily = np.repeat(price, 7, axis=1)[:, :N_DAYS]
price_eff = (price_daily.mean(axis=1, keepdims=True) / price_daily) ** 1.3
lam = base * dow_eff * trend * snap * evb * price_eff
# intermittency: many series have long zero stretches early on
launch = rng.integers(0, N_DAYS // 2, N_ITEMS)
sales = rng.poisson(lam).astype(np.int32)
for i, L in enumerate(launch):
    sales[i, :L] = 0

sales_df = pd.DataFrame(sales, columns=[f"d_{i+1}" for i in range(N_DAYS)])
sales_df.insert(0, "state_id", "CA")
sales_df.insert(0, "store_id", "CA_1")
sales_df.insert(0, "cat_id", "FOODS")
sales_df.insert(0, "dept_id", "FOODS_3")
sales_df.insert(0, "item_id", items)
sales_df.insert(0, "id", [f"{it}_CA_1_validation" for it in items])
sales_df.to_csv("data/raw/sales_train_validation.csv", index=False)

wk_of_day = np.array(wm_yr_wk)
rows = []
for i, it in enumerate(items):
    per_wk = pd.DataFrame({"wm_yr_wk": wk_of_day, "sell_price": price_daily[i]}).drop_duplicates("wm_yr_wk")
    per_wk.insert(0, "item_id", it); per_wk.insert(0, "store_id", "CA_1")
    rows.append(per_wk)
pd.concat(rows, ignore_index=True).to_csv("data/raw/sell_prices.csv", index=False)
print("fixture written:", N_ITEMS, "series x", N_DAYS, "days")

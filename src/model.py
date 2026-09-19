"""Model definitions. The researcher edits this file.

CONTRACT
--------
A model is fit only on data strictly prior to the fold origin and returns a 28-day-ahead
forecast for every series as a long frame [id, date, forecast].

To add a model: write a class with `name`, `config()`, and `forecast()`, then register it
in MODELS at the bottom. Do not touch the fold logic in src/backtest.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    HORIZON,
    Panel,
    build_frame,
    build_training_set,
    event_window_multipliers,
)


class SeasonalNaive:
    """Repeat the last fully observed week: forecast(d) = sales(d - 7k), k chosen so the
    source date is the most recent same-weekday date strictly before the origin."""

    name = "seasonal_naive"

    def config(self) -> dict:
        return {"kind": "seasonal_naive", "season": 7}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        origin_pos = panel.pos(origin)
        offsets = [(origin_pos - 7) + ((h - 1) % 7) for h in range(1, horizon + 1)]
        assert all(o < origin_pos for o in offsets), "seasonal naive would read at/after origin"
        preds = panel.values[:, offsets]
        dates = pd.DatetimeIndex(
            [pd.Timestamp(origin) + pd.Timedelta(days=h) for h in range(horizon)]
        )
        return pd.DataFrame(
            {
                "id": np.repeat(panel.ids, horizon),
                "date": np.tile(dates.to_numpy(), panel.values.shape[0]),
                "forecast": preds.reshape(-1).astype(float),
            }
        )


class LGBMBaseline:
    """One LightGBM across all series. Lags 7/14/28, rolling means 7/28, day-of-week,
    month, SNAP flag, event flag, sell price, item and store as categoricals."""

    name = "lgbm_baseline"

    # Determinism: fixed seed, deterministic=True, force_row_wise=True, and a fixed
    # thread count. Thread count matters — LightGBM's histogram sums are order-dependent,
    # so varying threads breaks four-decimal reproducibility.
    PARAMS = {
        "objective": "regression",
        "n_estimators": 300,
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_child_samples": 50,
        "colsample_bytree": 0.9,
        "subsample": 1.0,
        "reg_lambda": 1.0,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 4,
        "verbose": -1,
    }
    N_TRAIN_ORIGINS = 40
    TRAIN_ORIGIN_SPACING = 7
    # Subclasses (experiments) override FEATURES / PARAMS / origin settings / hooks. The
    # baseline keeps FEATURE_COLUMNS verbatim and adds no config keys, so its config hash
    # (900159c6f3dd, run r033) and metrics do not move.
    FEATURES: list[str] | None = None  # None = the bound dataset's FEATURE_COLUMNS

    @property
    def features(self) -> list[str]:
        return list(FEATURE_COLUMNS) if self.FEATURES is None else list(self.FEATURES)

    def config(self) -> dict:
        cfg = {
            "kind": "lgbm",
            "params": dict(self.PARAMS),
            "features": self.features,
            "n_train_origins": self.N_TRAIN_ORIGINS,
            "train_origin_spacing": self.TRAIN_ORIGIN_SPACING,
        }
        cfg.update(self.extra_config())
        return cfg

    def extra_config(self) -> dict:
        """Experiment-specific config keys; empty for the baseline."""
        return {}

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        """Post-fit hook (identity for the baseline): adjust raw predictions using only
        columns of the predict frame that are known in advance (calendar, price, horizon)."""
        return preds

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        model = lgb.LGBMRegressor(**params)

        features = self.features
        categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
        x_train = train[features]
        x_pred = predict[features].copy()
        # Align categorical dictionaries so LightGBM sees identical codes in both frames.
        for col in categorical:
            categories = x_train[col].cat.categories
            x_pred[col] = pd.Categorical(x_pred[col], categories=categories)

        model.fit(x_train, train["y"], categorical_feature=categorical)
        return model.predict(x_pred)

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        train = build_training_set(
            panel,
            origin,
            n_origins=self.N_TRAIN_ORIGINS,
            spacing_days=self.TRAIN_ORIGIN_SPACING,
            horizon=horizon,
        )
        predict = build_frame(panel, origin, horizon, with_target=False)
        preds = self._fit_predict(train, predict, seed)
        preds = self.postprocess(predict, preds)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


# ----------------------------------------------------------------------- experiments
# One class per experiment; each changes exactly one thing relative to its parent.


class LGBMChristmasZero(LGBMBaseline):
    """H031 (run r037, branch exp/r037; ported to the v3 contract): forecast 0 on Christmas
    Day. The store is closed every 25 December (sales 0 on 2012-2015) but the 40-origin
    training window never contains a Christmas, so the baseline forecasts a normal day
    inside folds 2 and 3. Reads the adapter's `christmas` calendar flag."""

    name = "lgbm_xmas0"

    def extra_config(self) -> dict:
        return {"postprocess": "christmas_zero"}

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        closed = predict["christmas"].to_numpy() == 1
        return np.where(closed, 0.0, preds)


# ----------------------------------------------------------------------- recipe (SPEC_v4 Part C)
# The published M5 recipe, added one ingredient at a time on top of the champion. Each class
# changes exactly one thing relative to its parent so the ledger records what it was worth.


class LGBMRecipe1Capacity(LGBMChristmasZero):
    """Ingredient 1: capacity with early stopping. Up to 3000 rounds at lr 0.02, deeper
    leaves, feature/bagging subsampling (seeded). The newest simulated training origin is
    held out as the validation set for early stopping (its 28-day target window closes
    before the fold origin, so no fold data is touched); the model is used as-is at its
    best iteration."""

    name = "recipe1_capacity"
    # SPEC_v4 asked for lr 0.02 / 3000 rounds; that exceeded the 60-minute screening budget
    # on this laptop (Tweedie fits ~8 min each). lr 0.05 / 1500 keeps the early-stopped
    # capacity idea at ~2.5x fewer trees; recorded as a deviation in the changelog.
    PARAMS = {
        **LGBMChristmasZero.PARAMS,
        "n_estimators": 1500, "learning_rate": 0.05, "num_leaves": 127,
        "min_child_samples": 100, "colsample_bytree": 0.7, "subsample": 0.7, "subsample_freq": 1,
    }
    EARLY_STOPPING_ROUNDS = 100

    def extra_config(self) -> dict:
        return {**super().extra_config(), "early_stopping": self.EARLY_STOPPING_ROUNDS, "validation": "newest_origin"}

    CALIBRATE = False
    CORRECTION = None  # v5 Part B: {"window": 28, "clip": [0.5, 2.0], "shrink": 0.5} or None (off)
    _val_buffer: list = []

    def _calibrate(self, va_frame: pd.DataFrame, va_pred: np.ndarray, pred_frame: pd.DataFrame, pred: np.ndarray) -> np.ndarray:
        """Post-fit adjustment from the validation window (the newest simulated origin's rows =
        the 28 days just before the fold origin). Leak-free: everything is before the origin."""
        return pred

    def _row_weights(self, train: pd.DataFrame):
        """Per-row sample weights for the fit, or None. Called on the exact frame each
        model is fit on (after the direct per-week split), so subclasses may derive the
        weights from the frame's own columns."""
        return None

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        features = self.features
        categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
        # rows from the newest simulated origin = validation; origin = target date - (h - 1)
        origin_of_row = train["date"] - pd.to_timedelta(train["horizon"].astype(int) - 1, unit="D")
        newest = origin_of_row.max()
        val_mask = (origin_of_row == newest).to_numpy()
        x_all = train[features]
        x_tr, y_tr = x_all[~val_mask], train["y"][~val_mask]
        x_va, y_va = x_all[val_mask], train["y"][val_mask]
        x_pred = predict[features].copy()
        for col in categorical:
            cats = x_tr[col].cat.categories
            x_va = x_va.assign(**{col: pd.Categorical(x_va[col], categories=cats)})
            x_pred[col] = pd.Categorical(x_pred[col], categories=cats)
        # optional per-row sample weights (subclass hook); None = plain unweighted fit
        w = self._row_weights(train)
        fit_kw = {} if w is None else {"sample_weight": w[~val_mask], "eval_sample_weight": [w[val_mask]]}
        model = lgb.LGBMRegressor(**params)
        model.fit(x_tr, y_tr, eval_set=[(x_va, y_va)], categorical_feature=categorical,
                  callbacks=[lgb.early_stopping(self.EARLY_STOPPING_ROUNDS, verbose=False)], **fit_kw)
        self.last_best_iteration = int(model.best_iteration_ or params["n_estimators"])
        out = model.predict(x_pred, num_iteration=model.best_iteration_)
        if self.CORRECTION:  # v5 Part B: keep this model's validation-window predictions for the fold-level correction
            self._val_buffer.append((train.loc[val_mask, "id"].to_numpy(), train.loc[val_mask, "y"].to_numpy(dtype=float),
                                     model.predict(x_va, num_iteration=model.best_iteration_)))
        if self.CALIBRATE:  # subclass hook; off by default so every other model is untouched
            va_pred = model.predict(x_va, num_iteration=model.best_iteration_)
            out = self._calibrate(train[val_mask], va_pred, predict, out)
        return out


class LGBMRecipe2Tweedie(LGBMRecipe1Capacity):
    """Ingredient 2: Tweedie objective (variance power 1.1) plus a per-series level-growth
    feature, level_ratio_28_365 (last-28-day mean over last-365-day mean, at the origin).
    The v0 lessons showed Tweedie's under-forecast is level growth between training and
    forecast windows (ledger H027); the feature lets the model see it."""

    name = "recipe2_tweedie"
    PARAMS = {**LGBMRecipe1Capacity.PARAMS, "objective": "tweedie", "tweedie_variance_power": 1.1}

    @property
    def features(self) -> list[str]:
        return super().features + ["level_ratio_28_365"]


def series_correction(va_id, va_y, va_pred, pred_id, window: int = 28, clip=(0.5, 2.0), shrink: float = 0.5) -> np.ndarray:
    """v5 Part B: per-series multiplicative correction from the validation window (the last
    `window` in-sample days before the origin, predicted by models that did not train on
    them). ratio = sum(actual) / sum(predicted) per series; factor = 1 + shrink * (ratio - 1),
    clipped to `clip`; series absent from the window (or with no predicted volume) get 1.
    Role-free: keyed on the contract's series id only."""
    g = pd.DataFrame({"id": va_id, "y": np.asarray(va_y, dtype=float), "p": np.asarray(va_pred, dtype=float)}).groupby("id", sort=False)[["y", "p"]].sum()
    ok = g["p"] > 1e-6
    ratio = pd.Series(1.0, index=g.index); ratio[ok] = g.loc[ok, "y"] / g.loc[ok, "p"]
    factor = (1.0 + shrink * (ratio - 1.0)).clip(clip[0], clip[1])
    return factor.reindex(pd.Index(pred_id)).fillna(1.0).to_numpy()


class LGBMRecipe3Direct(LGBMRecipe2Tweedie):
    """Ingredient 3: direct multi-horizon. One model per horizon week (h 1-7, 8-14, 15-21,
    22-28), each fit on that week's rows with target-relative lags tlag_7..tlag_35, which
    are defined only where the lagged day is strictly before the origin (k >= h). Week w
    therefore sees lags >= 7w; the rest are all-NaN in its rows and carry nothing."""

    name = "recipe3_direct"
    WEEKS = ((1, 7), (8, 14), (15, 21), (22, 28))

    @property
    def features(self) -> list[str]:
        return super().features + [f"tlag_{k}" for k in (7, 14, 21, 28, 35)]

    def extra_config(self) -> dict:
        return {**super().extra_config(), "direct_weeks": [list(w) for w in self.WEEKS]}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        out = np.empty(len(predict), dtype=float)
        th = train["horizon"].astype(int).to_numpy()
        ph = predict["horizon"].astype(int).to_numpy()
        if self.CORRECTION:
            self._val_buffer = []
        for lo, hi in self.WEEKS:
            tm = (th >= lo) & (th <= hi)
            pm = (ph >= lo) & (ph <= hi)
            out[pm] = super()._fit_predict(train[tm], predict[pm], seed)
        if self.CORRECTION:
            va_id = np.concatenate([b[0] for b in self._val_buffer]); va_y = np.concatenate([b[1] for b in self._val_buffer])
            va_p = np.concatenate([b[2] for b in self._val_buffer]); self._val_buffer = []
            out = out * series_correction(va_id, va_y, va_p, predict["id"].to_numpy(), **self.CORRECTION)
        return out


class LGBMRecipe4Rolling(LGBMRecipe3Direct):
    """Ingredient 4: rolling mean/std/max over 7/14/28/56/180 days at the origin, zero-run
    length, days since first sale, days since last sale (all strictly before the origin)."""

    name = "recipe4_rolling"
    ROLL_EXTRA = ([f"roll_mean_{w}" for w in (14, 56, 180)]
                  + [f"roll_std_{w}" for w in (7, 14, 28, 56, 180)]
                  + [f"roll_max_{w}" for w in (7, 14, 28, 56, 180)]
                  + ["zero_run_length", "days_since_first_sale", "days_since_last_sale"])

    @property
    def features(self) -> list[str]:
        return super().features + self.ROLL_EXTRA


class LGBMRecipe5Price(LGBMRecipe4Rolling):
    """Ingredient 5: price relative to the item's max to date, week-over-week price
    momentum, an on-promotion flag, price relative to the price group's mean that day, and
    the share of the group on promotion."""

    name = "recipe5_price"
    PRICE_EXTRA = ["price_rel_max", "price_momentum", "on_promo", "price_rel_group", "group_promo_share"]

    @property
    def features(self) -> list[str]:
        return super().features + self.PRICE_EXTRA


class LGBMRecipe6Calendar(LGBMRecipe5Price):
    """Ingredient 6: event lead/lag flags (+/-3 days), SNAP for the series' own state,
    day of month, week of year."""

    name = "recipe6_calendar"
    CAL_EXTRA = ([f"event_lead{k}" for k in (3, 2, 1)] + [f"event_lag{k}" for k in (1, 2, 3)]
                 + ["snap_own", "day_of_month", "week_of_year"])

    @property
    def features(self) -> list[str]:
        return super().features + self.CAL_EXTRA


# L2-objective variants of ingredients 3-6 (fallback chain on the ingredient-1 base): the
# Tweedie base under-forecast by 4-5% on m5_ca1 and every feature ingredient improved WAPE
# but not WRMSSE on top of it. Same features, same early stopping, L2 loss.
_L2 = {**LGBMRecipe1Capacity.PARAMS}


class LGBMRecipe3DirectL2(LGBMRecipe3Direct):
    name = "recipe3_direct_l2"; PARAMS = _L2


class LGBMRecipe4RollingL2(LGBMRecipe4Rolling):
    name = "recipe4_rolling_l2"; PARAMS = _L2


class LGBMRecipe5PriceL2(LGBMRecipe5Price):
    name = "recipe5_price_l2"; PARAMS = _L2


class LGBMRecipe6CalendarL2(LGBMRecipe6Calendar):
    name = "recipe6_calendar_l2"; PARAMS = _L2


class LGBMRecipe6CalendarL2YoY(LGBMRecipe6CalendarL2):
    """Generalization play (A): a same-weekday-last-year level anchor on top of the champion.

    The champion is DIRECT multi-horizon with as-of-origin features, so it carries the level
    of the recent (winter, in the backtest) history into the forecast window. The frozen
    yardstick evaluates a SPRING window the winter backtest folds never contain, and a
    winter-derived level under/over-shoots spring. `tlag_364` reads the actual sales at the
    same weekday roughly one year before EACH target day (source column origin_pos + h - 1 -
    364), which is always strictly before the origin (asserted in build_frame) since 364 >> 28
    — so it is leak-free by construction and gives the model last-spring's level to anchor to
    rather than only this-winter's. Everything else (features, L2 params, direct per-week fit,
    early stopping, Christmas zero) is recipe6_calendar_l2 unchanged."""

    name = "recipe6_calendar_l2_yoy"
    YOY_LAGS = (364,)  # same-weekday-last-year target-relative lag(s); leak-free (k >> horizon)

    @property
    def features(self) -> list[str]:
        return super().features + [f"tlag_{k}" for k in self.YOY_LAGS]

    def extra_config(self) -> dict:
        return {**super().extra_config(), "yoy_lags": list(self.YOY_LAGS)}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        train = build_training_set(
            panel, origin, n_origins=self.N_TRAIN_ORIGINS,
            spacing_days=self.TRAIN_ORIGIN_SPACING, horizon=horizon,
            extra_target_lags=self.YOY_LAGS,
        )
        predict = build_frame(panel, origin, horizon, with_target=False, extra_target_lags=self.YOY_LAGS)
        preds = self._fit_predict(train, predict, seed)
        preds = self.postprocess(predict, preds)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


class LGBMRecipe6CalendarL2YoYEaster(LGBMRecipe6CalendarL2):
    """Generalization play B: an Easter-phase-corrected same-weekday-last-year anchor.

    Refinement of the YoY anchor (H164). That anchor's whole gain was January holiday-echo; on
    the spring-facing folds it was net-negative because a fixed 364-day (52-week) lag MISALIGNS
    Easter — Easter is lunar and moves ~a week year to year, so 364 reads a normal pre-Easter
    Sunday instead of last Easter (every OTHER major US holiday is nth-weekday and 364 aligns it
    correctly). `tlag_yoy` uses shift (Easter_this - Easter_last) within +/- EASTER_WINDOW days of
    Easter and 364 elsewhere, so the anchor is phase-correct around Easter too. Leak-free: shift
    is always >= ~357 days, so the source column is strictly before the origin (asserted in
    build_frame). Everything else is recipe6_calendar_l2 unchanged. The decisive backtest read is
    folds 6-7 (Feb29/Mar14 origins straddle Easter 2016), which should turn non-negative."""

    name = "recipe6_calendar_l2_yoye"
    EASTER_WINDOW = 21  # +/- days around Easter where the phase correction applies

    @property
    def features(self) -> list[str]:
        return super().features + ["tlag_yoy"]

    def extra_config(self) -> dict:
        return {**super().extra_config(), "yoy_anchor": "easter_phase", "easter_window": self.EASTER_WINDOW}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        train = build_training_set(
            panel, origin, n_origins=self.N_TRAIN_ORIGINS,
            spacing_days=self.TRAIN_ORIGIN_SPACING, horizon=horizon,
            yoy_easter_window=self.EASTER_WINDOW,
        )
        predict = build_frame(panel, origin, horizon, with_target=False, yoy_easter_window=self.EASTER_WINDOW)
        preds = self._fit_predict(train, predict, seed)
        preds = self.postprocess(predict, preds)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


class LGBMRecipe6CalendarL2Hist3y(LGBMRecipe6CalendarL2):
    """Play B core lever: widen the training span from ~280 days to ~3 years at the SAME row
    count. The base uses 40 origins at 7-day spacing (280 days) — with a 28-day horizon each
    day is covered ~4x, so most of those rows are redundant overlap. Spacing 28 keeps 40 origins
    but spans ~1120 days (~3 years), trading intra-window redundancy for THREE prior years incl.
    prior springs — so the model has finally trained on the season it forecasts. Everything else
    is recipe6_calendar_l2 unchanged; only the training-origin spacing moves."""

    name = "recipe6_calendar_l2_hist3y"
    TRAIN_ORIGIN_SPACING = 28


class LGBMRecipe6CalendarL2YoYEHist3y(LGBMRecipe6CalendarL2YoYEaster):
    """Both play-B levers together: the Easter-phase YoY anchor (validated ingredient, r133) on
    top of the 3-year training span. The stack the year-round proxy should reward if both the
    spring-level anchor and the longer history generalize."""

    name = "recipe6_calendar_l2_yoye_h3y"
    TRAIN_ORIGIN_SPACING = 28


class LGBMRecipeSearch(LGBMRecipe6CalendarL2):
    """Config-driven recipe variant for the parameterized self-improvement loop. The orchestrator
    writes a JSON config to $KEPLER_SEARCH_CONFIG and runs this model; behaviour is fully
    determined by that file, so the loop searches the space WITHOUT writing code. config() embeds
    the whole config so every run's hash is unique and the variant is recoverable from its detail
    JSON. The holdout is never involved. Config keys (all optional):
      params: dict merged onto the L2 LightGBM params (num_leaves, min_child_samples, ...)
      train_origin_spacing / n_train_origins: training-window shape
      yoy_easter_window: int -> add the Easter-phase YoY anchor (tlag_yoy); null -> off
      extra_target_lags: [k, ...] -> add tlag_k features
      label: human note (recorded, not used)"""

    name = "recipe_search"

    def __init__(self):
        import json, os
        path = os.environ.get("KEPLER_SEARCH_CONFIG")
        self._cfg = json.load(open(path)) if path and os.path.exists(path) else {}
        self.PARAMS = {**_L2, **self._cfg.get("params", {})}
        self.TRAIN_ORIGIN_SPACING = int(self._cfg.get("train_origin_spacing", 7))
        self.N_TRAIN_ORIGINS = int(self._cfg.get("n_train_origins", 40))
        self._yoy_window = self._cfg.get("yoy_easter_window")  # None or int
        self._extra_lags = tuple(self._cfg.get("extra_target_lags", []))

    @property
    def features(self) -> list[str]:
        feats = list(super().features)
        feats += [f"tlag_{k}" for k in self._extra_lags]
        if self._yoy_window is not None:
            feats += ["tlag_yoy"]
        return feats

    def extra_config(self) -> dict:
        return {**super().extra_config(), "search_config": self._cfg}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        train = build_training_set(
            panel, origin, n_origins=self.N_TRAIN_ORIGINS,
            spacing_days=self.TRAIN_ORIGIN_SPACING, horizon=horizon,
            extra_target_lags=self._extra_lags, yoy_easter_window=self._yoy_window,
        )
        predict = build_frame(panel, origin, horizon, with_target=False,
                              extra_target_lags=self._extra_lags, yoy_easter_window=self._yoy_window)
        preds = self._fit_predict(train, predict, seed)
        preds = self.postprocess(predict, preds)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


class LGBMXmasThanksgivingDept(LGBMChristmasZero):
    """H041 (retest of H039 on the champion): multiply the Christmas-zeroed forecast on
    Thanksgiving Day and the three days after it by the department's mean prior-year ratio of
    that day to its four same-weekday days before (history strictly before the origin). No
    40-origin training window contains a Thanksgiving; no model input changes."""

    name = "lgbm_xmas0_tgd"

    def extra_config(self) -> dict:
        return {"postprocess": "christmas_zero+thanksgiving_dept4"}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        # predict rows are series-major (id repeated per horizon), matching reshape(-1)
        self._mult = event_window_multipliers(
            panel, panel.pos(origin), horizon, "Thanksgiving", "dept_id"
        ).reshape(-1)
        return super().forecast(panel, origin, horizon, seed)

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        return super().postprocess(predict, preds) * self._mult


class LGBMRecipe6CalendarL2Tweedie(LGBMRecipe6CalendarL2):
    """The full recipe under a Tweedie objective (variance power 1.1) instead of L2 regression.
    Tweedie handles the many zero-sales days differently; used as an ensemble member."""

    name = "recipe6_l2_tweedie"
    PARAMS = {**LGBMRecipe6CalendarL2.PARAMS, "objective": "tweedie", "tweedie_variance_power": 1.1}


class LGBMRecipeEnsembleObj(LGBMRecipe6CalendarL2):
    """Ensemble across objectives: the mean of the recipe under regression (recipe6_calendar_l2)
    and under Tweedie (recipe6_l2_tweedie). Diverse error structures cancel on averaging;
    aggregation-neutral (averages the bottom forecasts, so every level benefits from the
    variance reduction). Run with bag_seeds on (the harness averages across seeds too). 2x fit."""

    name = "recipe_ens_obj"

    def extra_config(self) -> dict:
        return {**super().extra_config(), "ensemble": ["recipe6_calendar_l2", "recipe6_l2_tweedie"]}

    def forecast(self, panel, origin, horizon=HORIZON, seed: int = 42):
        reg = super().forecast(panel, origin, horizon, seed)
        tw = LGBMRecipe6CalendarL2Tweedie().forecast(panel, origin, horizon, seed)
        m = reg.merge(tw, on=["id", "date"], suffixes=("_r", "_t"))
        m["forecast"] = 0.5 * (m["forecast_r"] + m["forecast_t"])
        return m[["id", "date", "forecast"]]


class LGBMRecipeEnsembleRD(LGBMRecipe6CalendarL2):
    """Recursive + direct ensemble (the M5 winners' core blend): the mean of the direct
    multi-horizon recipe (recipe6_calendar_l2) and the recursive 1-step model
    (src/recursive.py). Their errors are structured differently — the recipe fixes features
    at the origin, the recursive model compounds along the horizon — so averaging decorrelates.
    Aggregation-neutral. Run with bag_seeds on. Fits the recipe (4 direct models) plus one
    recursive model per seed."""

    name = "recipe_ens_rd"

    def extra_config(self) -> dict:
        return {**super().extra_config(), "ensemble": ["recipe6_calendar_l2", "lgbm_recursive_dbc"]}

    def forecast(self, panel, origin, horizon=HORIZON, seed: int = 42):
        from .recursive import RecursiveForecasterDebiased
        direct = super().forecast(panel, origin, horizon, seed)
        rec = RecursiveForecasterDebiased().forecast(panel, origin, horizon, seed)
        m = direct.merge(rec, on=["id", "date"], suffixes=("_d", "_r"))
        m["forecast"] = 0.5 * (m["forecast_d"] + m["forecast_r"])
        return m[["id", "date", "forecast"]]


class LGBMRecipeReconciled(LGBMRecipe6CalendarL2):
    """Middle-out multiplicative reconciliation (SPEC_v7): forecast a smooth aggregate level
    independently and scale the recipe's item-store forecasts within each group so their sum
    matches it. Borrows the aggregate's level to correct the bottom model's aggregate bias.
    Run with bag_seeds on (the harness averages the reconciled forecast across seeds), same as
    the recipe. See src/reconcile.py."""

    name = "recipe6_reconciled"
    RECON_LEVEL = ["store_id", "cat_id"]    # M5 level 8 (store-category): smooth, and the probe's best calm-fold level
    RECON_CLIP = (0.7, 1.5)                   # cap per-group scaling; folds 3-8 gains come from small bias corrections
    GATE_MAJOR_EVENT = True                  # skip reconciliation for the whole holiday window + aftermath (see reconcile.py)

    def extra_config(self) -> dict:
        return {**super().extra_config(), "reconcile_level": list(self.RECON_LEVEL),
                "reconcile_clip": list(self.RECON_CLIP), "gate_major_event": self.GATE_MAJOR_EVENT}

    def forecast(self, panel, origin, horizon=HORIZON, seed: int = 42):
        from . import reconcile as rec
        bottom = super().forecast(panel, origin, horizon, seed)
        if self.GATE_MAJOR_EVENT and rec.window_has_major_event(panel, origin, horizon):
            return bottom  # holiday window: the light aggregate model is unreliable, keep bottom-up
        agg = rec.aggregate_forecast(panel, self.RECON_LEVEL, origin, horizon, seed)
        return rec.reconcile(bottom, agg, panel, self.RECON_LEVEL, tuple(self.RECON_CLIP))


class LGBMRecipe6CalendarL2Slow(LGBMRecipe6CalendarL2):
    """Research lever (close the leaderboard gap): restore the spec learning schedule — a
    slower learning rate (0.02) with a higher tree cap (3000), early-stopped — from the
    budget schedule (0.05 / 1500) the recipe adopted for wall-clock in v4. Slower learning
    with more rounds usually lifts LightGBM accuracy at the cost of fit time. One variable:
    the learning schedule; every feature, the direct per-week split, the L2 objective and the
    bagging are recipe6_calendar_l2 unchanged."""

    name = "recipe6_l2_slow"
    PARAMS = {**LGBMRecipe6CalendarL2.PARAMS, "learning_rate": 0.02, "n_estimators": 3000}


class LGBMRecipe6CalendarL2Corr(LGBMRecipe6CalendarL2):
    """v5 Part B: the best recipe with the per-series correction ON (one variable vs
    recipe6_calendar_l2). Factor per series = 1 + 0.5 * (actual/predicted over the 28-day
    validation window - 1), clipped to [0.5, 2.0]; see series_correction()."""

    name = "recipe6_calendar_l2_corr"
    CORRECTION = {"window": 28, "clip": [0.5, 2.0], "shrink": 0.5}

    def extra_config(self) -> dict:
        return {**super().extra_config(), "series_correction": dict(self.CORRECTION)}


class LGBMRecipe6PerStore(LGBMRecipe6CalendarL2):
    """v5 Part C (recipe ingredient 7): one model chain per partition (roles["partition"],
    store_id on M5) instead of one global model. Every other setting is recipe6_calendar_l2:
    each partition gets its own direct per-week fits with early stopping on its own newest
    origin. Predictions are concatenated in the predict frame's row order and scored by the
    same frozen scorer. Role-driven: refuses a dataset that declares no partition."""

    name = "recipe6_per_store"

    def extra_config(self) -> dict:
        from . import features as _f
        return {**super().extra_config(), "partition": _f.PARTITION_COLUMN}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        from . import features as _f
        col = _f.PARTITION_COLUMN
        if not col:
            raise SystemExit(f"{self.name}: the dataset declares no roles['partition']; nothing to split on")
        tkey = train[col].astype(str).to_numpy(); pkey = predict[col].astype(str).to_numpy()
        out = np.empty(len(predict), dtype=float)
        for g in pd.unique(pkey):  # predict-frame order: deterministic
            tm, pm = tkey == g, pkey == g
            if not tm.any():
                raise SystemExit(f"{self.name}: partition {g!r} has no training rows")
            out[pm] = super()._fit_predict(train[tm], predict[pm], seed)
        return out


class LGBMRecipe6PerStoreCorr(LGBMRecipe6PerStore):
    """Per-partition recipe with the Part B per-series correction ON (for use only if Part B
    concludes ON)."""

    name = "recipe6_per_store_corr"
    CORRECTION = {"window": 28, "clip": [0.5, 2.0], "shrink": 0.5}

    def extra_config(self) -> dict:
        return {**super().extra_config(), "series_correction": dict(self.CORRECTION)}


class LGBMRecipeBag3(LGBMRecipe6CalendarL2):
    """Lever 2 (SPEC_v4): seed-averaged forecasts. forecast(seed) is the mean of three fits
    at sub-seeds derived from `seed`, so each logged seed is already a small ensemble. The
    harness's per-seed spread shrinks (~1/sqrt(3)) and the keep-rule bar with it; the
    variance reduction usually also improves the mean. 3x the fit cost."""

    name = "recipe_bag3"
    BAG = 3

    def extra_config(self) -> dict:
        return {**super().extra_config(), "bag": self.BAG}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        preds = [super(LGBMRecipeBag3, self)._fit_predict(train, predict, seed + 1000 * k) for k in range(self.BAG)]
        return np.mean(preds, axis=0)


class LGBMRecipeScaled(LGBMRecipeBag3):
    """Bias fix 1 (SPEC_v4 lever 1): predict a RATIO, not a level. The training target is
    y / scale where scale = the series' 28-day mean at the origin (the roll_mean_28 feature,
    floored so zero-history series fall back to an unscaled target); predictions are
    multiplied back by the same scale. Trees cannot extrapolate a level they have not seen;
    a level-invariant target lets growth between the training window and the forecast
    window pass straight through. Everything else as recipe_bag3."""

    name = "recipe_scaled"
    SCALE_FEATURE = "roll_mean_28"
    SCALE_FLOOR = 0.1  # below this the series is essentially dormant; use the raw target

    def extra_config(self) -> dict:
        return {**super().extra_config(), "target_scale": self.SCALE_FEATURE, "scale_floor": self.SCALE_FLOOR}

    def _scale(self, frame: pd.DataFrame) -> np.ndarray:
        s = frame[self.SCALE_FEATURE].to_numpy(dtype=float)
        return np.where(s >= self.SCALE_FLOOR, s, 1.0)

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        s_tr = self._scale(train)
        scaled = train.assign(y=train["y"].to_numpy(dtype=float) / s_tr)
        return super()._fit_predict(scaled, predict, seed) * self._scale(predict)


class LGBMRecipeMomentum(LGBMRecipeBag3):
    """Bias fix 2: momentum ratios at the origin (7/28, 28/56, 28/180-day level ratios) on
    the bagged recipe, so the model can lift or lower a forecast for a series whose level
    is moving. (First planned on the ratio target; that base lost, r109.)"""

    name = "recipe_momentum"

    @property
    def features(self) -> list[str]:
        return super().features + ["mom_7_28", "mom_28_56", "mom_28_180"]


class LGBMRecipeScaledW(LGBMRecipeScaled):
    """Bias fix 1b: the ratio target with level-proportional sample weights (weight = the
    scale), so the L2 loss on ratios is a level-weighted loss and high-volume series keep
    their importance -- the unweighted ratio target (r109) let low-volume series' noisy
    ratios dominate and over-forecast by +2.7%. The weights enter through the capacity
    fit's _row_weights hook, so the direct per-week models and the 3-bag are unchanged.
    (r111, the first attempt, bypassed both loops and timed out; it is not a result.)"""

    name = "recipe_scaled_w"

    def extra_config(self) -> dict:
        return {**super().extra_config(), "sample_weight": self.SCALE_FEATURE}

    def _row_weights(self, train: pd.DataFrame):
        return self._scale(train)


class LGBMRecipeCalib(LGBMRecipeBag3):
    """Bias fix 4: per store x department calibration on the bagged recipe. Each fitted
    model's predictions on its early-stopping validation window (the 28 days just before
    the origin; for the direct per-week models, that week's slice of it) are compared with
    the actuals per (store, department); the forecast is multiplied by
    (sum actual + w) / (sum prediction + w), which shrinks toward 1 for small groups, and is
    clipped to [0.8, 1.25]. Costs no extra fit. Targets the calm-month aggregate-level
    under-forecast (r107 folds 4-7) that the ratio target (r109) and momentum features
    (r110) did not fix."""

    name = "recipe_calib"
    CALIBRATE = True
    GROUP = ("store_id", "dept_id")
    CLIP = (0.8, 1.25)
    PRIOR_WEIGHT = 200.0  # units of predicted volume over the window

    def extra_config(self) -> dict:
        return {**super().extra_config(), "calibration": {"group": list(self.GROUP), "window": "validation_origin",
                                                          "clip": list(self.CLIP), "prior_weight": self.PRIOR_WEIGHT}}

    def _calibrate(self, va_frame, va_pred, pred_frame, pred):
        keys = list(self.GROUP)
        g = pd.DataFrame({"y": va_frame["y"].to_numpy(dtype=float), "p": np.asarray(va_pred, dtype=float)})
        for k in keys:
            g[k] = va_frame[k].astype(str).to_numpy()
        agg = g.groupby(keys, sort=False)[["y", "p"]].sum()
        factor = ((agg["y"] + self.PRIOR_WEIGHT) / (agg["p"] + self.PRIOR_WEIGHT)).clip(*self.CLIP)
        idx = pd.MultiIndex.from_arrays([pred_frame[k].astype(str).to_numpy() for k in keys], names=keys)
        f = factor.reindex(idx).fillna(1.0).to_numpy()
        self.last_calibration = {"/".join(k): round(v, 4) for k, v in factor.items()}
        return pred * f


from .recursive import RecursiveForecaster as _RecursiveForecaster, RecursiveForecasterTweedie as _RecursiveForecasterTweedie, RecursiveForecasterLog as _RecursiveForecasterLog, RecursiveForecasterSqrt as _RecursiveForecasterSqrt, RecursiveForecasterDebiased as _RecursiveForecasterDebiased

class LGBMDirectMH(LGBMRecipe6CalendarL2):
    """SPEC v9 Part D (Researcher A, lever=horizon): multi-horizon direct models with a variable
    bucket count. The champion is already 4-bucket direct (WEEKS weekly); this makes bucket count
    the one experimental variable. Each bucket fits its own model on that horizon range's rows,
    using only target-relative lags valid for it (the k>=h NaN rule -> a bucket starting at horizon
    h sees lags >= h). No recursion, so no compounding bias. N_BUCKETS splits 1..28 into even
    contiguous ranges: 4 == champion (sanity), 7 (4-day), 28 (per-day)."""

    name = "lgbm_direct_mh"
    N_BUCKETS = 4

    @property
    def WEEKS(self):
        import math
        n = max(1, min(self.N_BUCKETS, HORIZON))
        size = math.ceil(HORIZON / n)
        return tuple((i + 1, min(i + size, HORIZON)) for i in range(0, HORIZON, size))

    def extra_config(self) -> dict:
        return {**super().extra_config(), "n_buckets": self.N_BUCKETS, "buckets": [list(w) for w in self.WEEKS]}


class LGBMDirectMH7(LGBMDirectMH):
    name = "lgbm_direct_mh7"; N_BUCKETS = 7


class LGBMDirectMH28(LGBMDirectMH):
    name = "lgbm_direct_mh28"; N_BUCKETS = 28


MODELS: dict[str, type] = {
    SeasonalNaive.name: SeasonalNaive,
    LGBMBaseline.name: LGBMBaseline,
    LGBMChristmasZero.name: LGBMChristmasZero,
    LGBMRecipe1Capacity.name: LGBMRecipe1Capacity,
    LGBMRecipe2Tweedie.name: LGBMRecipe2Tweedie,
    LGBMRecipe3Direct.name: LGBMRecipe3Direct,
    LGBMRecipe4Rolling.name: LGBMRecipe4Rolling,
    LGBMRecipe5Price.name: LGBMRecipe5Price,
    LGBMRecipe6Calendar.name: LGBMRecipe6Calendar,
    LGBMRecipe3DirectL2.name: LGBMRecipe3DirectL2,
    LGBMRecipe4RollingL2.name: LGBMRecipe4RollingL2,
    LGBMRecipe5PriceL2.name: LGBMRecipe5PriceL2,
    LGBMRecipe6CalendarL2.name: LGBMRecipe6CalendarL2,
    LGBMRecipe6CalendarL2YoY.name: LGBMRecipe6CalendarL2YoY,
    LGBMRecipe6CalendarL2YoYEaster.name: LGBMRecipe6CalendarL2YoYEaster,
    LGBMRecipe6CalendarL2Hist3y.name: LGBMRecipe6CalendarL2Hist3y,
    LGBMRecipe6CalendarL2YoYEHist3y.name: LGBMRecipe6CalendarL2YoYEHist3y,
    LGBMRecipeSearch.name: LGBMRecipeSearch,
    LGBMDirectMH.name: LGBMDirectMH,
    LGBMDirectMH7.name: LGBMDirectMH7,
    LGBMDirectMH28.name: LGBMDirectMH28,
    LGBMRecipe6CalendarL2Corr.name: LGBMRecipe6CalendarL2Corr,
    LGBMRecipe6CalendarL2Slow.name: LGBMRecipe6CalendarL2Slow,
    LGBMRecipeReconciled.name: LGBMRecipeReconciled,
    LGBMRecipe6CalendarL2Tweedie.name: LGBMRecipe6CalendarL2Tweedie,
    LGBMRecipeEnsembleObj.name: LGBMRecipeEnsembleObj,
    LGBMRecipeEnsembleRD.name: LGBMRecipeEnsembleRD,
    _RecursiveForecaster.name: _RecursiveForecaster,
    _RecursiveForecasterTweedie.name: _RecursiveForecasterTweedie,
    _RecursiveForecasterLog.name: _RecursiveForecasterLog,
    _RecursiveForecasterSqrt.name: _RecursiveForecasterSqrt,
    _RecursiveForecasterDebiased.name: _RecursiveForecasterDebiased,
    LGBMRecipe6PerStore.name: LGBMRecipe6PerStore,
    LGBMRecipe6PerStoreCorr.name: LGBMRecipe6PerStoreCorr,
    LGBMRecipeBag3.name: LGBMRecipeBag3,
    LGBMRecipeScaled.name: LGBMRecipeScaled,
    LGBMRecipeMomentum.name: LGBMRecipeMomentum,
    LGBMRecipeScaledW.name: LGBMRecipeScaledW,
    LGBMRecipeCalib.name: LGBMRecipeCalib,


    LGBMXmasThanksgivingDept.name: LGBMXmasThanksgivingDept,
}


def get_model(name: str):
    if name not in MODELS:
        raise SystemExit(f"Unknown model '{name}'. Registered: {', '.join(sorted(MODELS))}")
    return MODELS[name]()

"""
【中文】河水温度 → 火电降额 → 系统供电缺口（docs/PIPELINE_SPEC.md M-18，关系 R-P0 / R-W5）。

    T_w(d)  = μ + (α − μ) / (1 + exp(γ (β − T̄_a7(d))))           Mohseni 等（1998）的 logistic 河温模型，
                                                                  T̄_a7 为 BNA 前 7 天平均气温
    ΔP_g(t) = P_g · max( clip((T_w − T_lim) / span, 0, 1),  1[Q < Q_min] · f_low )
    Sh(t)   = max(0, L(t) − (a · C_sys + P_imp − Σ_g ΔP_g(t)))       系统缺口（MW）
    shed(t) = Sh(t) / L(t)                                         按比例轮流停电（假设各地均摊）

只考虑直流冷却（EIA-860 冷却类型 OC / ON）且从 Cumberland 河取水的火电厂；水电的低流量出力不在本步。

River temperature → thermal derating → system shortfall (PIPELINE_SPEC M-18, relations R-P0 / R-W5).
Only once-through cooled thermal plants drawing on the Cumberland River are included.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

F_TO_C = lambda f: (np.asarray(f, float) - 32.0) * 5.0 / 9.0  # noqa: E731


def mohseni(ta, mu, alpha, beta, gamma):
    """【中文】Mohseni 等（1998）logistic 河温–气温关系 / logistic stream–air temperature relation."""
    return mu + (alpha - mu) / (1.0 + np.exp(gamma * (beta - ta)))


def tdec_mainstem(path, river="Cumberland River") -> pd.DataFrame:
    """【中文】TDEC 地表水化学数据中干流的水温采样 / main-stem water-temperature samples from TDEC."""
    d = pd.read_csv(path, encoding="latin-1", low_memory=False,
                    usecols=["Monitoring Location Name", "County", "DWR Station ID", "Activity Date",
                             "Characteristic Name", "Result", "Result Unit"])
    d = d[(d["Characteristic Name"] == "Temperature, water") & (d["Monitoring Location Name"] == river)
          & (d["Result Unit"] == "deg C")]
    return pd.DataFrame({"date": pd.to_datetime(d["Activity Date"], format="%m/%d/%Y", errors="coerce").dt.date,
                         "station": d["DWR Station ID"], "county": d["County"],
                         "tw_c": pd.to_numeric(d["Result"], errors="coerce")}).dropna()


def daily_air(asos: pd.DataFrame, tz: str) -> pd.Series:
    """【中文】ASOS 逐小时 → 当地日平均气温（°C）/ local-day mean air temperature."""
    t = pd.to_datetime(asos["valid"], utc=True).dt.tz_convert(tz)
    s = pd.Series(F_TO_C(pd.to_numeric(asos["tmpf"], errors="coerce")), index=t).dropna()
    return s.groupby(s.index.date).mean()


def fit_stream_temperature(samples: pd.DataFrame, ta_daily: pd.Series, window: int = 7) -> dict:
    """【中文】把每个采样日与前 window 天平均气温配对，非线性最小二乘拟合 Mohseni 模型。
    Fit the Mohseni model to samples paired with the preceding window-day mean air temperature."""
    ta7 = ta_daily.sort_index().rolling(window, min_periods=window - 1).mean()
    x = samples["date"].map(ta7)
    ok = x.notna()
    x, y = x[ok].to_numpy(float), samples.loc[ok, "tw_c"].to_numpy(float)
    p0 = [max(0.0, y.min()), y.max() + 1.0, np.median(x), 0.2]
    p, cov = curve_fit(mohseni, x, y, p0=p0, bounds=([0, 15, -10, 0.01], [15, 40, 35, 2.0]), maxfev=20000)
    resid = y - mohseni(x, *p)
    return {"mu": p[0], "alpha": p[1], "beta": p[2], "gamma": p[3], "window_days": window,
            "n_samples": int(len(y)), "rmse_c": float(np.sqrt(np.mean(resid ** 2))),
            "r2": float(1 - np.var(resid) / np.var(y)), "ta7_range_c": [float(x.min()), float(x.max())],
            "tw_range_c": [float(y.min()), float(y.max())], "param_se": np.sqrt(np.diag(cov)).tolist()}


def river_temperature(model: dict, ta_daily: pd.Series, delta_c: float = 0.0) -> pd.Series:
    """【中文】由日气温（可加情景增量）推算日河温 / daily river temperature, optionally warmed by delta."""
    ta7 = ta_daily.sort_index().rolling(model["window_days"], min_periods=model["window_days"] - 1).mean() + delta_c
    return pd.Series(mohseni(ta7.to_numpy(float), model["mu"], model["alpha"], model["beta"], model["gamma"]),
                     index=ta7.index)


def read_usgs_rdb(path) -> pd.Series:
    """【中文】USGS RDB 日均流量（cfs）/ USGS RDB daily discharge."""
    rows = [ln.split("\t") for ln in open(path, encoding="utf-8") if ln.startswith("USGS")]
    df = pd.DataFrame(rows).iloc[:, :4]
    df.columns = ["agency", "site", "date", "q"]
    return pd.Series(pd.to_numeric(df["q"], errors="coerce").to_numpy(),
                     index=pd.to_datetime(df["date"]).dt.date).dropna()


def eia860_plants(zip_path, ba="TVA", water="Cumberland", cooling=("OC", "ON")) -> tuple[pd.DataFrame, float]:
    """【中文】从 EIA-860 找出某平衡区内、从指定水体取水的直流冷却电厂及其夏季容量；同时返回该平衡区总夏季容量。
    Once-through cooled plants of a balancing authority drawing on a named water body, plus the BA's
    total operable summer capacity."""
    import zipfile

    with zipfile.ZipFile(zip_path) as z:
        def sheet(prefix, name=0):
            f = next(n for n in z.namelist() if n.startswith(prefix))
            with z.open(f) as fh:
                return pd.read_excel(fh, sheet_name=name, header=1)
        plant = sheet("2___Plant")
        gen = sheet("3_1_Generator", "Operable")
        cool = sheet("6_2_EnviroEquip", "Cooling")
    plant = plant[plant["Balancing Authority Code"] == ba]
    gen = gen[gen["Plant Code"].isin(plant["Plant Code"])]
    cap = pd.to_numeric(gen["Summer Capacity (MW)"], errors="coerce").groupby(gen["Plant Code"]).sum()
    c = cool[cool["Plant Code"].isin(plant["Plant Code"]) & (cool["Cooling Status"] == "OP")
             & cool["Cooling Type 1"].isin(cooling) & cool["Cooling Water Source"].astype(str).str.contains(water, case=False)]
    p = (c.groupby("Plant Code").agg(cooling_type=("Cooling Type 1", "first"), water_source=("Cooling Water Source", "first"))
         .join(plant.set_index("Plant Code")[["Plant Name", "County", "State", "Latitude", "Longitude"]]))
    p["summer_capacity_mw"] = p.index.map(cap)
    return p.reset_index().rename(columns={"Plant Code": "plant_code", "Plant Name": "plant_name"}), float(cap.sum())


def shed_fraction(tw_c: np.ndarray, q_cfs: np.ndarray, load_mw: np.ndarray, plant_mw: float, c_sys: float,
                  th: dict) -> tuple[np.ndarray, np.ndarray]:
    """【中文】逐小时火电降额（MW）与轮流停电比例；th 为 C-P9.* 的抽样（长度 N）。返回 (N, H) 两个数组。
    Hourly derate (MW) and shed share for N parameter draws (C-P9.*); returns two (N, H) arrays."""
    col = lambda k: np.asarray(th[k], float)[:, None]  # noqa: E731
    temp = np.clip((tw_c[None, :] - col("C-P9")) / col("C-P9.span"), 0, 1)
    low = (q_cfs[None, :] < col("C-P9.Qmin")) * col("C-P9.flow")
    derate = plant_mw * np.maximum(temp, low)
    supply = col("C-P9.avail") * c_sys + col("C-P9.imp") - derate
    L = np.atleast_2d(load_mw)          # 【中文】(H,) 或 (N, H) / one load series or one per run
    shed = np.where(np.isfinite(L) & (L > 0), np.maximum(0.0, L - supply) / np.maximum(L, 1.0), 0.0)
    return derate, shed

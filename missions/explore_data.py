"""SETUP-02 — Khám phá dữ liệu đầu vào của Lab 25.

Chạy: python missions/explore_data.py
Trả lời 3 câu hỏi DoD:
  1. 4 file CSV có đủ và trông như thế nào?
  2. GPU nào có gpu_util_pct cao nhưng achieved_tflops thấp? (GPU-Util lie)
  3. interruptible=1 nghĩa là gì -> job nào ứng cử spot?
"""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"


def _load():
    return (
        pd.read_csv(DATA / "price_catalog.csv"),
        pd.read_csv(DATA / "gpu_telemetry.csv"),
        pd.read_csv(DATA / "token_usage.csv"),
        pd.read_csv(DATA / "workloads.csv"),
    )


def section(title):
    print(f"\n{'=' * 66}\n  {title}\n{'=' * 66}")


def main():
    price, tel, tok, work = _load()

    section("1. BANG GIA GPU (price_catalog.csv)")
    p = price.copy()
    p["$/TFLOP-hr"] = (p["on_demand_hr"] / p["peak_tflops_fp16"] * 1000).round(3)
    p["$/GB-VRAM-hr"] = (p["on_demand_hr"] / p["hbm_gb"]).round(4)
    p["spot_off%"] = ((1 - p["spot_hr"] / p["on_demand_hr"]) * 100).round(1)
    p["rsv3y_off%"] = ((1 - p["reserved_3yr_hr"] / p["on_demand_hr"]) * 100).round(1)
    print(p[["gpu_type", "on_demand_hr", "spot_hr", "reserved_3yr_hr", "spot_off%",
             "rsv3y_off%", "peak_tflops_fp16", "peak_bw_tbs", "watts",
             "$/TFLOP-hr", "$/GB-VRAM-hr"]].to_string(index=False))

    section("2. TELEMETRY: GPU-UTIL vs MFU (gpu_telemetry.csv)")
    peak = price.set_index("gpu_type")
    t = tel.copy()
    t["peak_tflops"] = t["gpu_type"].map(peak["peak_tflops_fp16"])
    t["peak_bw"] = t["gpu_type"].map(peak["peak_bw_tbs"])
    t["mfu"] = t["achieved_tflops"] / t["peak_tflops"]
    t["mbu"] = t["achieved_bw_tbs"] / t["peak_bw"]

    g = (t.groupby(["gpu_id", "gpu_type", "workload"])
           .agg(util=("gpu_util_pct", "mean"), mfu=("mfu", "mean"),
                mbu=("mbu", "mean"), power_w=("power_w", "mean"), hours=("ts", "count"))
           .reset_index().sort_values("mfu"))
    g[["util", "mfu", "mbu", "power_w"]] = g[["util", "mfu", "mbu", "power_w"]].round(3)
    print(g.to_string(index=False))

    lies = g[(g["util"] >= 90) & (g["mfu"] < 0.30)]
    idle_rows = t[t["gpu_util_pct"] < 10]
    print(f"\n>> GPU-UTIL LIE (util>=90% VA mfu<30%): {list(lies['gpu_id']) or 'khong co'}")
    for _, r in lies.iterrows():
        od = peak.loc[r["gpu_type"], "on_demand_hr"]
        print(f"   {r['gpu_id']:<14} util={r['util']:.1f}%  MFU={r['mfu']:.3f}"
              f"  -> tra ${od}/h nhung chi nhan ~{r['mfu'] * 100:.0f}% FLOPs")
    idle_cost = float(idle_rows["gpu_type"].map(peak["on_demand_hr"]).sum())
    print(f"\n>> GIO IDLE (util<10%, tinh theo tung GIO chu khong phai trung binh ngay): "
          f"{len(idle_rows)} gio")
    for gid, n in idle_rows.groupby("gpu_id").size().items():
        print(f"   {gid:<14} {n} gio idle / 24")
    print(f"   lang phi = ${idle_cost:,.2f}/ngay  ->  ${idle_cost * 30:,.0f}/thang")

    section("3. TOKEN USAGE (token_usage.csv)")
    k = tok.copy()
    k["total_tok"] = k["input_tokens"] + k["output_tokens"]
    print(f"requests={len(k):,}  tong token={k['total_tok'].sum():,}")
    print(f"cached_input / input = {k['cached_input_tokens'].sum() / k['input_tokens'].sum():.1%}")
    print(f"is_batch=1     : {k['is_batch'].mean():.1%} traffic")
    print(f"is_reasoning=1 : {k['is_reasoning'].mean():.1%} traffic"
          f"  ({k.loc[k['is_reasoning'] == 1, 'total_tok'].sum() / k['total_tok'].sum():.1%} token)")
    print("\nroute_tier:")
    print(k.groupby("route_tier").agg(requests=("model", "size"),
                                      tokens=("total_tok", "sum")).to_string())
    print("\ntheo team:")
    print(k.groupby("team").agg(requests=("model", "size"), tokens=("total_tok", "sum"))
           .sort_values("tokens", ascending=False).to_string())
    print(f"\ntag coverage (team+project khong rong): "
          f"{(k['team'].notna() & k['project'].notna()).mean():.1%}")

    section("4. WORKLOADS (workloads.csv)")
    w = work.copy()
    w["duty%"] = (w["hours_per_day"] / 24 * 100).round(1)
    w["gpu_hours"] = w["hours_per_day"] * w["days"] * w["num_gpus"]
    w["on_demand_$"] = (w["gpu_hours"] * w["gpu_type"].map(peak["on_demand_hr"])).round(0)
    w["ung_vien"] = w.apply(
        lambda r: "spot" if r["interruptible"] == 1
        else ("reserved" if r["hours_per_day"] / 24 >= 0.55 else "on_demand"), axis=1)
    print(w[["job_id", "team", "kind", "gpu_type", "num_gpus", "hours_per_day",
             "days", "duty%", "interruptible", "gpu_hours", "on_demand_$",
             "ung_vien"]].to_string(index=False))
    print(f"\ntong chi phi on-demand cua 8 job: ${w['on_demand_$'].sum():,.0f}")
    print(f"job interruptible=1: {int(w['interruptible'].sum())}/{len(w)} "
          f"-> co the chay spot + checkpoint, va co the doi vung (carbon-aware)")


if __name__ == "__main__":
    main()

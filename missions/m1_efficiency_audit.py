"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics

DAYS = 30
HEADROOM = 1.25   # keep 25% spare capacity when proposing a smaller GPU
MFU_TARGET = 0.35  # metrics.py: healthy training MFU is ~0.35-0.45
MBU_TARGET = 0.60  # metrics.py: decode target on H100-80GB


def unit_prices(cat: dict) -> list:
    """Per-GPU unit economics: $/GB-VRAM-hr and $/TB/s-hr alongside $/GPU-hr.

    EXT-02 — $/GPU-hr answers "what does the box cost", not "what does the box give
    you". For a memory-bound workload the meaningful denominators are VRAM capacity
    and HBM bandwidth, not FLOPs.
    """
    out = []
    for g, c in cat.items():
        od = num(c["on_demand_hr"])
        out.append({
            "gpu_type": g, "on_demand_hr": od,
            "hbm_gb": num(c["hbm_gb"]), "peak_bw_tbs": num(c["peak_bw_tbs"]),
            "peak_tflops": num(c["peak_tflops_fp16"]),
            "usd_per_gb_hr": round(od / num(c["hbm_gb"]), 4) if num(c["hbm_gb"]) else 0.0,
            "usd_per_tbs_hr": round(od / num(c["peak_bw_tbs"]), 3) if num(c["peak_bw_tbs"]) else 0.0,
            "usd_per_tflop_hr": round(od / num(c["peak_tflops_fp16"]) * 1000, 3) if num(c["peak_tflops_fp16"]) else 0.0,
        })
    return sorted(out, key=lambda r: r["usd_per_gb_hr"])


def rightsize_by_mbu(tel: list, cat: dict, headroom: float = HEADROOM) -> list:
    """Propose a cheaper GPU for each device, sized on what it ACTUALLY consumed.

    A GPU is memory-bound when its MBU runs well ahead of its MFU: it is moving bytes
    faster than it is doing math, so bandwidth and VRAM — not FLOPs — set the floor.

    Only GPUs that are genuinely over-provisioned (below BOTH targets) are candidates;
    a healthy device is left alone however cheap the alternatives look. The replacement
    must clear the observed bandwidth, FLOPs and peak VRAM with headroom, and must
    actually be cheaper — otherwise we keep what we have.
    """
    obs = defaultdict(lambda: {"bw": [], "tflops": [], "mem": [], "type": None})
    for r in tel:
        o = obs[r["gpu_id"]]
        o["type"] = r["gpu_type"]
        o["bw"].append(num(r["achieved_bw_tbs"]))
        o["tflops"].append(num(r["achieved_tflops"]))
        o["mem"].append(num(r["mem_used_gb"]))

    rows = []
    for gid, o in obs.items():
        cur = o["type"]
        cur_od = num(cat[cur]["on_demand_hr"])
        peak_bw = num(cat[cur]["peak_bw_tbs"])
        peak_fp = num(cat[cur]["peak_tflops_fp16"])
        mbu = metrics.compute_mbu(sum(o["bw"]) / len(o["bw"]), peak_bw)
        mfu = metrics.compute_mfu(sum(o["tflops"]) / len(o["tflops"]), peak_fp)
        need_bw = max(o["bw"]) * headroom
        need_fp = max(o["tflops"]) * headroom
        need_mem = max(o["mem"]) * headroom

        fits = [
            (num(c["on_demand_hr"]), g) for g, c in cat.items()
            if num(c["peak_bw_tbs"]) >= need_bw
            and num(c["peak_tflops_fp16"]) >= need_fp
            and num(c["hbm_gb"]) >= need_mem
        ]
        best_od, best = min(fits) if fits else (cur_od, cur)
        over_provisioned = mfu < MFU_TARGET and mbu < MBU_TARGET
        if not over_provisioned or best_od >= cur_od:
            best_od, best = cur_od, cur
        ratio = mbu / mfu if mfu > 0 else 0.0
        regime = "memory-bound" if ratio >= 1.10 else ("compute-bound" if ratio <= 0.90 else "balanced")
        rows.append({
            "gpu_id": gid, "current": cur, "proposed": best,
            "regime": regime, "over_provisioned": over_provisioned,
            "verdict": "right-size" if best != cur else ("keep (healthy)" if not over_provisioned else "keep (no cheaper fit)"),
            "mfu": round(mfu, 3), "mbu": round(mbu, 3),
            "need_bw_tbs": round(need_bw, 3), "need_mem_gb": round(need_mem, 1),
            "peak_mem_gb": round(max(o["mem"]), 1),
            "vram_headroom_pct": round((num(cat[cur]["hbm_gb"]) / max(o["mem"]) - 1) * 100, 1) if max(o["mem"]) else 0.0,
            "usd_per_gb_now": round(cur_od / num(cat[cur]["hbm_gb"]), 4),
            "usd_per_gb_new": round(best_od / num(cat[best]["hbm_gb"]), 4),
            "monthly_now": round(cur_od * 24 * DAYS),
            "monthly_new": round(best_od * 24 * DAYS),
            "monthly_savings": round(max(0.0, cur_od - best_od) * 24 * DAYS),
        })
    return sorted(rows, key=lambda r: -r["monthly_savings"])


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")

    # --- EXT-02: right-size on what the GPU actually consumed, not on $/GPU-hr ---
    units = unit_prices(cat)
    rightsize = rightsize_by_mbu(tel, cat)
    rightsize_total = sum(r["monthly_savings"] for r in rightsize)

    if verbose:
        print("\n-- EXT-02: unit economics ($/GPU-hr hides this) --")
        print(f"{'GPU':8}{'$/hr':>7}{'VRAM':>6}{'BW TB/s':>9}{'$/GB-hr':>10}{'$/TBs-hr':>10}{'$/TFLOP-hr':>12}")
        for u in units:
            print(f"{u['gpu_type']:8}{u['on_demand_hr']:>7.2f}{u['hbm_gb']:>6.0f}{u['peak_bw_tbs']:>9.2f}"
                  f"{u['usd_per_gb_hr']:>10.4f}{u['usd_per_tbs_hr']:>10.3f}{u['usd_per_tflop_hr']:>12.3f}")
        print("\n-- EXT-02: right-sizing proposals (headroom x1.25) --")
        print(f"{'GPU':13}{'regime':14}{'MFU':>6}{'MBU':>6}{'now':>7}{'->':>4}{'proposed':>9}"
              f"{'$/mo now':>10}{'$/mo new':>10}{'saves':>8}  verdict")
        for r in rightsize:
            print(f"{r['gpu_id']:13}{r['regime']:14}{r['mfu']:>6.3f}{r['mbu']:>6.3f}{r['current']:>7}{'->':>4}"
                  f"{r['proposed']:>9}{r['monthly_now']:>10,}{r['monthly_new']:>10,}"
                  f"{r['monthly_savings']:>8,}  {r['verdict']}")
        print(f"total right-size savings: ${rightsize_total:,}/month")
        tight = [r for r in rightsize if r["vram_headroom_pct"] < 25]
        if tight:
            print(f"\nVRAM headroom < 25% on {len(tight)} GPUs — memory, not FLOPs, is the binding constraint:")
            for r in tight:
                print(f"  {r['gpu_id']:13}{r['current']:7} peak {r['peak_mem_gb']:>5.1f} GB used"
                      f" / {num(cat[r['current']]['hbm_gb']):>3.0f} GB  -> {r['vram_headroom_pct']:>5.1f}% spare")

    return {"summary": summary, "lies": lies, "idle_waste_daily": round(idle_waste, 2),
            "unit_prices": units, "rightsize": rightsize,
            "rightsize_monthly_savings": rightsize_total}


if __name__ == "__main__":
    run()

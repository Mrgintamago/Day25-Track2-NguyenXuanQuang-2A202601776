"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing

DAYS = 30


def run(verbose: bool = True, policy: str = "v1") -> dict:
    """policy='v1' = the simple documented rule; 'v2' = the EXT-01 cost-based policy."""
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        if policy == "v2":
            row = {k: (num(v) if k.endswith("_hr") else v) for k, v in c.items()}
            d = pricing.recommend_tier_detailed(
                hpd, interruptible, row, gpu_type=gtype, job_days=num(j["days"]))
            tier = d["tier"]
            # detailed policy prices ONE gpu over the horizon; scale to the job's fleet
            opt_cost = d["cost"] * ngpu
            # on-demand for the same (possibly shorter) horizon, for a fair comparison
            on_demand_cost = d["candidates"]["on_demand"] * ngpu
        else:
            tier = pricing.recommend_tier(hpd, interruptible)
            if tier == "spot":
                sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od)
                opt_cost = sim["spot_cost"]
            elif tier == "reserved":
                opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
            else:
                opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    if verbose:
        print(f"== M3 Purchasing Strategy (policy={policy}) ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "optimized_monthly": round(optimized_monthly), "savings_pct": round(savings_pct, 1)}


if __name__ == "__main__":
    run()

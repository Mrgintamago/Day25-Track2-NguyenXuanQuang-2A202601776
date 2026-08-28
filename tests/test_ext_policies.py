"""Tests for the 'Your Turn' extensions (EXT-01 purchasing policy, EXT-02 right-sizing)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finops import pricing
from missions import m1_efficiency_audit as m1
from missions import m3_purchasing as m3
from missions._common import catalog_by_type, num

H100 = {"gpu_type": "H100", "on_demand_hr": 2.5, "spot_hr": 1.5,
        "reserved_1yr_hr": 2.0, "reserved_3yr_hr": 1.4}


# --------------------------- EXT-01 ---------------------------

def test_legacy_policy_is_unchanged():
    """The simple rule must keep working when no price row is supplied."""
    assert pricing.recommend_tier(2, True) == "spot"
    assert pricing.recommend_tier(24, False) == "reserved"
    assert pricing.recommend_tier(4, False) == "on_demand"


def test_reserved_discount_read_from_catalog_not_hardcoded():
    cat = catalog_by_type()
    row = {k: (num(v) if k.endswith("_hr") else v) for k, v in cat["B200"].items()}
    d3 = pricing.reserved_discount_for(row)
    assert 0.36 < d3 < 0.38                                  # real B200 3yr discount, not 0.45
    assert pricing.break_even_utilization(d3) > 0.62         # needs >15h/day, not 13.2h


def test_interrupt_rate_varies_by_gpu_type():
    assert pricing.spot_interrupt_rate("A10G") > pricing.spot_interrupt_rate("H100")
    assert pricing.spot_interrupt_rate("unknown-gpu") == pricing.DEFAULT_INTERRUPT_RATE


def test_short_campaign_cannot_carry_a_long_commitment():
    """A 14-day job uses ~1% of a 3-year term, so no commitment may be recommended."""
    util = pricing.commitment_utilization(hours_per_day=20, demand_days=14, term_days=1095)
    assert util < 0.02
    d = pricing.recommend_tier_detailed(20, True, H100, gpu_type="H100", job_days=14)
    assert not d["tier"].startswith("reserved")
    assert d["recurring"] is False


def test_steady_workload_prefers_the_term_it_can_actually_see():
    """365 days of visibility clears a 1yr term but not a 3yr one."""
    d = pricing.recommend_tier_detailed(24, False, H100, gpu_type="H100", job_days=30)
    assert d["recurring"] is True
    assert "reserved_1yr" in d["candidates"]
    assert "reserved_3yr" not in d["candidates"]
    assert d["tier"] == "reserved_1yr"


def test_ties_go_to_the_least_binding_option():
    flat = dict(H100, reserved_1yr_hr=2.5)   # priced identically to on-demand at 24h duty
    d = pricing.recommend_tier_detailed(24, False, flat, gpu_type="H100", job_days=30)
    assert d["tier"] == "on_demand"


def test_v2_policy_runs_and_still_saves_money():
    r = m3.run(verbose=False, policy="v2")
    assert r["optimized_monthly"] < r["on_demand_monthly"]
    assert {x["tier"] for x in r["recommendations"]} & {"spot"}


# --------------------------- EXT-02 ---------------------------

def test_unit_prices_rank_differently_than_dollars_per_hour():
    units = m1.unit_prices(catalog_by_type())
    by_gb = [u["gpu_type"] for u in units]
    by_hr = [u["gpu_type"] for u in sorted(units, key=lambda x: x["on_demand_hr"])]
    assert by_gb[0] == "MI300X"      # cheapest VRAM
    assert by_hr[0] == "L4"          # cheapest box
    assert by_gb != by_hr            # the two rankings disagree — that is the lesson


def test_rightsizing_leaves_healthy_gpus_alone():
    r = m1.run(verbose=False)
    rows = {x["gpu_id"]: x for x in r["rightsize"]}
    healthy = rows["gpu-h100-0"]
    assert healthy["mfu"] >= 0.35
    assert healthy["proposed"] == healthy["current"]
    assert healthy["monthly_savings"] == 0


def test_rightsizing_targets_the_util_lie_gpu():
    r = m1.run(verbose=False)
    rows = {x["gpu_id"]: x for x in r["rightsize"]}
    lie = rows["gpu-h100-4"]
    assert lie["over_provisioned"] is True
    assert lie["proposed"] != lie["current"]
    assert lie["monthly_savings"] > 0
    assert r["rightsize_monthly_savings"] > 0


def test_proposed_replacement_clears_observed_bandwidth_and_memory():
    """Only rows where we actually propose a swap must satisfy the sizing constraints."""
    cat = catalog_by_type()
    swaps = [r for r in m1.run(verbose=False)["rightsize"] if r["proposed"] != r["current"]]
    assert swaps, "expected at least one right-sizing proposal"
    for row in swaps:
        c = cat[row["proposed"]]
        assert num(c["peak_bw_tbs"]) >= row["need_bw_tbs"]
        assert num(c["hbm_gb"]) >= row["need_mem_gb"]


def test_vram_headroom_is_reported():
    """VRAM — not FLOPs — is what the fleet is actually close to running out of."""
    rows = m1.run(verbose=False)["rightsize"]
    assert all("vram_headroom_pct" in r for r in rows)
    assert any(r["vram_headroom_pct"] < 25 for r in rows)

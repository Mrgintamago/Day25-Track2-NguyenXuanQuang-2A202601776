"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    price_row: dict | None = None,
    gpu_type: str | None = None,
    job_days: float | None = None,
) -> str:
    """Pick a purchasing tier from a workload's duty cycle + interruptibility.

    Simple policy (default, kept for backwards compatibility):
      - interruptible & not 24/7  -> 'spot'      (checkpoint and ride the discount)
      - duty cycle >= break-even  -> 'reserved'  (steady, high utilization)
      - otherwise                 -> 'on_demand' (spiky / low duty)

    Pass `price_row` (a price_catalog row) to switch on the EXT-01 policy, which
    prices spot per GPU type, honours the job's real duration, and lets the 1yr and
    3yr terms compete. Reserved terms collapse back to 'reserved' here; call
    recommend_tier_detailed() when you need the term and the runner-up.
    """
    if price_row is not None:
        d = recommend_tier_detailed(
            hours_per_day, interruptible, price_row,
            gpu_type=gpu_type,
            job_days=HORIZON_DAYS if job_days is None else job_days,
        )
        return "reserved" if d["tier"].startswith("reserved") else d["tier"]

    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        return "spot"
    if duty >= be:
        return "reserved"
    return "on_demand"


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }

# ---------------------------------------------------------------------------
# EXT-01 — a purchasing policy that knows about interruption risk and horizon
# ---------------------------------------------------------------------------

# Per-hour spot reclaim probability by GPU type. Derived from the catalog itself:
# the market prices reclaim risk into the spot discount, so the cheapest-relative
# spot (A10G -60%, L4 -56%) is also the most frequently reclaimed.
SPOT_INTERRUPT_RATE = {
    "H100": 0.03, "H200": 0.04, "B200": 0.06,
    "MI300X": 0.06, "A100": 0.05, "A10G": 0.12, "L4": 0.15,
}
DEFAULT_INTERRUPT_RATE = 0.05

# A commitment bills every hour of its term, used or not.
RESERVED_TERM_DAYS = {"reserved_1yr_hr": 365, "reserved_3yr_hr": 1095}

HORIZON_DAYS = 30  # planning/billing window used for comparisons
# How far ahead the business can actually see demand. You may only commit as far as
# you can see: this is what separates a 1-year from a 3-year term.
DEMAND_VISIBILITY_DAYS = 365


def spot_interrupt_rate(gpu_type: str | None) -> float:
    """Per-hour reclaim probability for a GPU type (falls back to the fleet default)."""
    return SPOT_INTERRUPT_RATE.get(gpu_type or "", DEFAULT_INTERRUPT_RATE)


def reserved_discount_for(row: dict, term: str = "reserved_3yr_hr") -> float:
    """Actual discount of a commitment term, read from the price catalog row.

    The catalog's real 3yr discounts span 37.1%-44.1%, so a hardcoded 0.45 puts the
    break-even line in the wrong place for every GPU except H100/A100.
    """
    od = float(row.get("on_demand_hr", 0) or 0)
    rv = float(row.get(term, 0) or 0)
    if od <= 0 or rv <= 0:
        return 0.0
    return max(0.0, 1.0 - rv / od)


def commitment_utilization(hours_per_day: float, demand_days: float, term_days: float) -> float:
    """Fraction of a commitment's billed hours the workload actually consumes.

    Duty cycle alone is not enough. A commitment bills 24h/day for its whole term,
    so utilization = duty x (days you will actually use it / days you are billed for).
    A job at 83% duty running for 14 days consumes ~1% of a 3-year term.
    """
    if term_days <= 0:
        return 0.0
    duty = max(0.0, hours_per_day) / 24.0
    coverage = min(1.0, max(0.0, demand_days) / term_days)
    return duty * coverage


def recommend_tier_detailed(
    hours_per_day: float,
    interruptible: bool,
    price_row: dict,
    gpu_type: str | None = None,
    job_days: float = HORIZON_DAYS,
    horizon_days: float = HORIZON_DAYS,
    recurring: bool | None = None,
    demand_visibility_days: float = DEMAND_VISIBILITY_DAYS,
) -> dict:
    """Cost-based tier choice over a planning horizon (EXT-01 policy).

    Improvements over the simple policy:
      1. spot is *priced*, not assumed — per-GPU-type interruption rate feeds
         spot_checkpoint_cost(), so a job on a frequently-reclaimed A10G can lose
         to reserved even though it is interruptible;
      2. commitments are only eligible for work that recurs, and only as far ahead
         as demand is actually visible — a one-off 14-day campaign (the `days`
         column in workloads.csv) cannot carry a 1,095-day term;
      3. break-even comes from the catalog's real discount per GPU, not 0.45;
      4. reserved_1yr and reserved_3yr compete against each other.

    Returns the winning tier plus every candidate's horizon cost, so callers can
    show the runner-up and the margin.
    """
    gpu_type = gpu_type or price_row.get("gpu_type")
    od_hr = float(price_row["on_demand_hr"])
    duty = max(0.0, hours_per_day) / 24.0
    # a job whose campaign covers the whole horizon is treated as steady-state work
    if recurring is None:
        recurring = job_days >= horizon_days
    billed_days = min(job_days, horizon_days) if not recurring else horizon_days
    gpu_hours = hours_per_day * billed_days

    candidates: dict = {"on_demand": gpu_hours * od_hr}

    if interruptible:
        sim = spot_checkpoint_cost(
            gpu_hours, float(price_row["spot_hr"]), od_hr,
            interrupt_rate=spot_interrupt_rate(gpu_type),
        )
        candidates["spot"] = sim["spot_cost"]

    # you may only commit as far as demand is visible; one-off work sees only itself
    demand_days = demand_visibility_days if recurring else job_days
    for term, term_days in RESERVED_TERM_DAYS.items():
        if term not in price_row:
            continue
        util = commitment_utilization(hours_per_day, demand_days, term_days)
        be = break_even_utilization(reserved_discount_for(price_row, term))
        # a commitment bills 24h/day for the whole horizon, used or not
        if util >= be:
            candidates[term.replace("_hr", "")] = float(price_row[term]) * 24.0 * billed_days

    # ties go to the least binding option — flexibility is worth something at equal cost
    lock_in = {"on_demand": 0, "spot": 1, "reserved_1yr": 2, "reserved_3yr": 3}
    ranked = sorted(candidates.items(), key=lambda kv: (round(kv[1], 2), lock_in.get(kv[0], 9)))
    tier = ranked[0][0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    return {
        "tier": tier,
        "cost": round(candidates[tier], 2),
        "candidates": {k: round(v, 2) for k, v in candidates.items()},
        "runner_up": runner_up[0] if runner_up else None,
        "margin_usd": round(runner_up[1] - candidates[tier], 2) if runner_up else 0.0,
        "duty": round(duty, 3),
        "recurring": recurring,
        "demand_days": demand_days,
        "interrupt_rate": spot_interrupt_rate(gpu_type),
        "break_even_3yr": round(break_even_utilization(reserved_discount_for(price_row)), 3),
    }

# everything number-y the app needs (velocity, baselines, eta, patterns)
# is derived here from the same ledger - either live bunq or cached json

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Iterable

DATA_PATH = Path(__file__).parent / "bunq_data.json"

WINDOW_DAYS = 30  # rolling window for velocity + patterns


def _load() -> dict:
    with open(DATA_PATH) as f:
        return json.load(f)


def _parse_date(s: str) -> date:
    return datetime.fromisoformat(s).date() if "T" in s else date.fromisoformat(s)


def _try_live_transactions() -> list[dict] | None:
    # pull from sandbox if we have a key, else None and the caller falls back
    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from bunq_client import BunqClient
        c = BunqClient(api_key=api_key, sandbox=True)
        c.authenticate()
        account_id = c.get_primary_account_id()
        raw = c.list_payments(account_id, limit=100)
        if not raw:
            return None
        out = []
        for p in raw:
            out.append({
                "date": (p.get("created") or "")[:10],
                "amount": p["amount"],
                # bunq doesn't categorise payments, infer from description
                "category": _infer_category(p.get("description", "")),
                "description": p.get("description", ""),
            })
        return out
    except Exception as e:
        print(f"[ledger] live bunq failed, using cache: {e}")
        return None


CATEGORY_KEYWORDS = {
    "clothing":       ["zara", "h&m", "nike", "jacket", "shoes", "sneakers", "coat", "shirt"],
    "groceries":      ["albert heijn", "jumbo", "lidl", "supermarket", "groceries"],
    "food_dining":    ["cafe", "restaurant", "lunch", "dinner", "takeaway", "uber eats"],
    "transport":      ["ns ", "ov-", "uber", "train", "metro", "fuel", "shell", "bp "],
    "entertainment":  ["netflix", "spotify", "cinema", "concert", "ticket"],
    "electronics":    ["apple", "samsung", "macbook", "iphone", "headphones"],
    "home":           ["ikea", "lamp", "chair", "decor"],
    "beauty":         ["sephora", "douglas", "lipstick", "perfume"],
    "income":         ["salary", "stipend", "top-up", "topup", "sugar daddy"],
}


def _infer_category(description: str) -> str:
    text = description.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in text for k in kws):
            return cat
    return "other"


def load_ledger() -> dict:
    # live if we can, cached otherwise. shape stays the same either way
    data = _load()
    live = _try_live_transactions()
    if live:
        data["transactions"] = live
        data["source"] = "bunq_sandbox"
    else:
        data["source"] = "cached"
    return data


def _filter_recent(txns: Iterable[dict], window: int = WINDOW_DAYS) -> list[dict]:
    today = date.today()
    cutoff = today - timedelta(days=window)
    return [t for t in txns if _parse_date(t["date"]) >= cutoff]


def daily_velocity(txns: list[dict] | None = None) -> dict:
    # (income - expenses) / window. components included so the UI can show the math
    if txns is None:
        txns = load_ledger()["transactions"]
    recent = _filter_recent(txns) or txns  # short history? use everything
    inflows  = sum(t["amount"]  for t in recent if t["amount"] > 0)
    outflows = sum(-t["amount"] for t in recent if t["amount"] < 0)
    days = max(1, WINDOW_DAYS)
    velocity = round((inflows - outflows) / days, 2)
    return {
        "daily_velocity_eur": velocity,
        "window_days": days,
        "inflows_eur": round(inflows, 2),
        "outflows_eur": round(outflows, 2),
    }


def category_baselines(txns: list[dict] | None = None) -> dict[str, float]:
    # avg single-purchase per category in eur. uses full ledger so it doesn't jitter
    if txns is None:
        txns = load_ledger()["transactions"]
    by_cat: dict[str, list[float]] = defaultdict(list)
    for t in txns:
        if t["amount"] >= 0:
            continue
        by_cat[t["category"]].append(-t["amount"])
    return {cat: round(mean(amts), 2) for cat, amts in by_cat.items() if amts}


def recent_purchases(category: str, txns: list[dict] | None = None) -> dict:
    # what's been happening in this category lately. drives the
    # "you've already bought 3 of these this month" type messages
    if txns is None:
        txns = load_ledger()["transactions"]
    recent = _filter_recent(txns)
    in_cat = [t for t in recent if t["category"] == category and t["amount"] < 0]
    today = date.today()
    full = [t for t in txns if t["category"] == category and t["amount"] < 0]
    last_date = max((_parse_date(t["date"]) for t in full), default=None)
    days_since = (today - last_date).days if last_date else 9999
    return {
        "count_this_month": len(in_cat),
        "total_this_month_eur": round(sum(-t["amount"] for t in in_cat), 2),
        "last_purchase_days_ago": days_since,
    }


def goal_status(txns: list[dict] | None = None) -> dict:
    # goal + a derived eta: today + (target - current) / velocity
    data = load_ledger()
    g = data["goal"]
    v = daily_velocity(txns or data["transactions"])["daily_velocity_eur"]
    remaining = max(0.0, g["target_eur"] - g["current_eur"])
    if v > 0:
        eta = date.today() + timedelta(days=round(remaining / v))
    else:
        eta = _parse_date(g["target_date"])  # no velocity, just use whatever date the user set
    return {
        "name": g["name"],
        "target_eur": g["target_eur"],
        "current_eur": g["current_eur"],
        "remaining_eur": round(remaining, 2),
        "current_eta": eta.isoformat(),
        "user_target_date": g["target_date"],
    }


def forecast_goal_impact(price_eur: float, txns: list[dict] | None = None) -> dict:
    # how this purchase shifts the goal eta
    g = goal_status(txns)
    v = daily_velocity(txns)["daily_velocity_eur"]
    delay = round(price_eur / v) if v > 0 else 0
    new_eta = _parse_date(g["current_eta"]) + timedelta(days=delay)
    return {
        "goal_name": g["name"],
        "current_eta": g["current_eta"],
        "new_eta": new_eta.isoformat(),
        "delay_days": delay,
        "daily_velocity_eur": v,
    }


def carbon_factors() -> dict[str, float]:
    return load_ledger().get("carbon_factors_kg_per_eur", {})


def carbon_for_purchase(price_eur: float, category: str) -> dict:
    # kg co2e + a comparison people can actually picture
    factors = carbon_factors()
    factor = factors.get(category, factors.get("other", 0.20))
    kg = round(price_eur * factor, 2)
    if kg <= 0:
        eq = "negligible footprint"
    elif kg < 5:
        eq = f"≈ {kg / 3:.1f} beef burgers"
    elif kg < 50:
        eq = f"≈ {round(kg / 0.18)} km of driving"
    else:
        years = kg / 21.0
        eq = (f"≈ {round(years * 12)} months of a tree's offset"
              if years < 2
              else f"≈ {years:.1f} years of a mature tree's CO₂ offset")
    return {"kg_co2e": kg, "equivalent": eq, "factor_kg_per_eur": factor}


if __name__ == "__main__":
    import json as _j
    print(_j.dumps({
        "velocity": daily_velocity(),
        "baselines": category_baselines(),
        "goal": goal_status(),
        "forecast_300": forecast_goal_impact(300),
        "carbon_jacket": carbon_for_purchase(300, "clothing"),
    }, indent=2))

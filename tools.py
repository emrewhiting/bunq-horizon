"""Tools the agent calls to gather financial context.

Each tool tries to hit Person A's backend; falls back to demo values if unavailable.
This means /analyze still works perfectly even if A's backend is down or slow.
"""
import os
from datetime import datetime, timedelta
import httpx
from dotenv import load_dotenv

load_dotenv()

PERSON_A_BASE = os.getenv("PERSON_A_BASE_URL", "http://localhost:8000")

# ---- Hardcoded demo values (locked to match the team's demo brief) ----
FALLBACK_VELOCITY = 15.0  # €/day discretionary surplus

FALLBACK_BASELINES = {
    "clothing": 120.0,
    "electronics": 200.0,
    "food_dining": 25.0,
    "groceries": 75.0,
    "transport": 30.0,
    "entertainment": 40.0,
    "beauty": 50.0,
    "home": 80.0,
    "other": 60.0,
}

FALLBACK_GOAL = {
    "name": "Tokyo 2026",
    "target": 3000.0,
    "current": 1800.0,
    "current_eta": "Aug 4",
}

FALLBACK_RECENT_PURCHASES = {
    "clothing": {
        "count_this_month": 3,
        "total_this_month": 340.00,
        "last_purchase_days_ago": 11,
    },
    "electronics": {
        "count_this_month": 0,
        "total_this_month": 0,
        "last_purchase_days_ago": 95,
    },
    "food_dining": {
        "count_this_month": 14,
        "total_this_month": 280,
        "last_purchase_days_ago": 1,
    },
}


def _try_get(path: str, params: dict | None = None) -> dict | None:
    """Try Person A's backend. Return None on any failure."""
    try:
        with httpx.Client(timeout=2.0) as c:
            resp = c.get(f"{PERSON_A_BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


# ---- Tool functions ----

def get_savings_velocity() -> dict:
    """How much surplus the user generates per day, excluding rent/salary/recurring."""
    real = _try_get("/api/savings_velocity")
    if real and "daily_discretionary_velocity" in real:
        return {"daily_velocity_eur": real["daily_discretionary_velocity"]}
    return {"daily_velocity_eur": FALLBACK_VELOCITY, "source": "fallback"}


def get_goal_status() -> dict:
    """User's primary savings goal: name, target, current."""
    real = _try_get("/api/accounts")
    if real:
        goal = next((a for a in real if a.get("is_goal")), None)
        if goal:
            return {
                "name": goal["description"].split("|")[0].strip(),
                "target": goal["target"],
                "current": goal["balance"],
            }
    return FALLBACK_GOAL | {"source": "fallback"}


def get_category_baseline(category: str) -> dict:
    """Average single-purchase amount in this category."""
    real = _try_get("/api/home_baseline", params={"category": category})
    if real and "amount_eur" in real:
        return {"category": category, "average_per_purchase": real["amount_eur"]}
    return {
        "category": category,
        "average_per_purchase": FALLBACK_BASELINES.get(category, 60.0),
        "source": "fallback",
    }


def find_personal_pattern(category: str) -> dict:
    """Surface a relevant behavioral pattern in recent transactions for this category."""
    real = _try_get("/api/recent_purchases", params={"category": category})
    data = real if real else FALLBACK_RECENT_PURCHASES.get(
        category,
        {"count_this_month": 1, "total_this_month": 50, "last_purchase_days_ago": 30},
    )

    count = data["count_this_month"]
    total = data["total_this_month"]
    days_since = data["last_purchase_days_ago"]

    if count >= 3:
        return {
            "type": "frequency_alert",
            "summary": f"{count + 1}th {category} purchase this month",
            "context": f"€{total:.0f} already spent on {category} this month",
        }
    elif days_since > 60:
        months = days_since // 30
        return {
            "type": "first_in_a_while",
            "summary": f"first {category} purchase in {months} months",
            "context": f"you typically buy {category} every few months",
        }
    else:
        return {
            "type": "on_pace",
            "summary": "in line with your normal spending",
            "context": f"{count} {category} purchases in the last 30 days",
        }


def forecast_goal_impact(price_eur: float) -> dict:
    """Compute how a new purchase would delay the savings goal."""
    velocity = get_savings_velocity()["daily_velocity_eur"]
    goal = get_goal_status()

    delay_days = round(price_eur / velocity) if velocity > 0 else 0

    # Get current ETA — use goal's current_eta if it's hardcoded, else compute
    if "current_eta" in goal:
        # parse "Aug 4" → datetime
        try:
            current_eta = datetime.strptime(f"{goal['current_eta']} 2026", "%b %d %Y")
        except ValueError:
            current_eta = datetime.now() + timedelta(days=(goal["target"] - goal["current"]) / velocity)
    else:
        days_now = (goal["target"] - goal["current"]) / velocity if velocity > 0 else 0
        current_eta = datetime.now() + timedelta(days=days_now)

    new_eta = current_eta + timedelta(days=delay_days)

    return {
        "goal_name": goal["name"],
        "current_eta": current_eta.strftime("%b %d"),
        "new_eta": new_eta.strftime("%b %d"),
        "delay_days": delay_days,
    }


# ---- Test it ----
if __name__ == "__main__":
    import json
    print("=== get_savings_velocity ===")
    print(json.dumps(get_savings_velocity(), indent=2))
    print("\n=== get_goal_status ===")
    print(json.dumps(get_goal_status(), indent=2))
    print("\n=== get_category_baseline('clothing') ===")
    print(json.dumps(get_category_baseline("clothing"), indent=2))
    print("\n=== find_personal_pattern('clothing') ===")
    print(json.dumps(find_personal_pattern("clothing"), indent=2))
    print("\n=== forecast_goal_impact(300) ===")
    print(json.dumps(forecast_goal_impact(300), indent=2))
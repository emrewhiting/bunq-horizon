"""Turns (item, category, price) into a Perspective Card.

The agent loop asks Claude what tool to run, runs it, feeds the result back,
then expects a JSON card. If the API call fails or no key is set,
build_card_directly() produces the same shape from ledger.py alone.
"""

from __future__ import annotations

import json
import os
from datetime import date

from dotenv import load_dotenv

import ledger

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


# Tools the agent can call. Each one is a thin wrapper around ledger.py so
# every number the agent uses is derived, not hardcoded.

def _tool_velocity():
    return ledger.daily_velocity()

def _tool_goal():
    return ledger.goal_status()

def _tool_baseline(category: str):
    base = ledger.category_baselines().get(category)
    if base is None:
        return {"category": category, "average_per_purchase_eur": None,
                "note": "no prior purchases in this category"}
    return {"category": category, "average_per_purchase_eur": base}

NO_HISTORY_DAYS = 365  # anything older counts as no real history


def _tool_pattern(category: str):
    p = ledger.recent_purchases(category)
    count = p["count_this_month"]
    total = p["total_this_month_eur"]
    days = p["last_purchase_days_ago"]

    if days >= NO_HISTORY_DAYS:
        return {"type": "no_history",
                "summary": f"no {category} purchases on record",
                "context": "first time buying in this category"}

    if count >= 3:
        return {"type": "frequency_alert",
                "summary": f"{count + 1}th {category} purchase this month",
                "context": f"€{total:.0f} already spent on {category} this window"}

    if days > 60:
        months = max(1, days // 30)
        return {"type": "first_in_a_while",
                "summary": f"first {category} purchase in {months} months",
                "context": "you don't usually buy this category"}

    return {"type": "on_pace",
            "summary": "in line with your normal spending",
            "context": f"{count} {category} purchase(s) in the last 30 days"}

def _tool_forecast(price_eur: float):
    return ledger.forecast_goal_impact(price_eur)

def _tool_carbon(price_eur: float, category: str):
    return ledger.carbon_for_purchase(price_eur, category)


TOOL_FNS = {
    "get_savings_velocity":  lambda **_: _tool_velocity(),
    "get_goal_status":       lambda **_: _tool_goal(),
    "get_category_baseline": lambda **kw: _tool_baseline(kw["category"]),
    "find_personal_pattern": lambda **kw: _tool_pattern(kw["category"]),
    "forecast_goal_impact":  lambda **kw: _tool_forecast(float(kw["price_eur"])),
    "estimate_carbon":       lambda **kw: _tool_carbon(float(kw["price_eur"]), kw["category"]),
}


TOOL_SCHEMAS = [
    {"name": "get_savings_velocity",
     "description": "Return the user's daily savings velocity in EUR, computed from inflows minus outflows in the last 30 days.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_goal_status",
     "description": "Return the primary savings goal: name, target, current balance, derived ETA.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_category_baseline",
     "description": "Return the average single-purchase amount for a category, computed from history.",
     "input_schema": {"type": "object",
                      "properties": {"category": {"type": "string"}},
                      "required": ["category"]}},
    {"name": "find_personal_pattern",
     "description": "Return a behavioural pattern for this category: frequency_alert, first_in_a_while, or on_pace.",
     "input_schema": {"type": "object",
                      "properties": {"category": {"type": "string"}},
                      "required": ["category"]}},
    {"name": "forecast_goal_impact",
     "description": "Return how a purchase of price_eur shifts the goal ETA in days and dates.",
     "input_schema": {"type": "object",
                      "properties": {"price_eur": {"type": "number"}},
                      "required": ["price_eur"]}},
    {"name": "estimate_carbon",
     "description": "Return embodied kg CO2e for the purchase plus a relatable equivalent.",
     "input_schema": {"type": "object",
                      "properties": {"price_eur": {"type": "number"},
                                     "category": {"type": "string"}},
                      "required": ["price_eur", "category"]}},
]


SYSTEM_PROMPT = """You are bunq Horizon, a financial-clarity feature for bunq, the bank of The Free.

You receive an item the user is considering buying with its price. Your job: produce a Perspective Card that gives the user one moment of clarity. The user decides; you only inform.

Voice rules:
- Inform, never judge. No "you should" or "you shouldn't".
- Approved phrases: "your call", "for context", "heads up", "in line with".
- Two short lines. Concrete. No emoji, no exclamation marks.
- Treat the user as a capable adult.

Workflow:
1. Call forecast_goal_impact with the price.
2. Call get_category_baseline with the item's category to compute the ratio (price ÷ baseline).
3. Call find_personal_pattern with the category for a behavioural insight.
4. Call estimate_carbon with price + category.
5. Synthesise the card.

Output: a single raw JSON object, nothing else, no fences.
Schema:
{
  "headline":     "ITEM_NAME — €PRICE",
  "impact_line":  "Pushes [GOAL] from [OLD_DATE] → [NEW_DATE]",
  "context_line": "~[N] days at your pace · [Nx] your usual [category] spend",
  "carbon_line":  "[X] kg CO2e · [equivalent]",
  "footer":       "Your call.",
  "actions": [
    {"label": "Plan it", "action": "draft_transfer"},
    {"label": "Not now", "action": "log_skip"}
  ]
}

Format dates as "Aug 4" (no year). If a baseline is null, drop the "Nx your usual" comparison and just keep the days at pace."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in: {text[:200]}")
    return json.loads(text[start:end + 1])


def run_agent(item: str, category: str, price: float) -> dict:
    """Run the tool-use loop until Claude returns the final card."""
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return build_card_directly(item, category, price)

    try:
        from anthropic import Anthropic
    except ImportError:
        return build_card_directly(item, category, price)

    client = Anthropic()
    user_msg = (f"The user is considering buying:\n"
                f"- Item: {item}\n- Category: {category}\n- Price: €{price}\n\n"
                f"Use your tools, then return the Perspective Card JSON.")

    messages = [{"role": "user", "content": user_msg}]

    for _ in range(8):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=1500,
                system=SYSTEM_PROMPT, tools=TOOL_SCHEMAS, messages=messages,
            )
        except Exception as e:
            print(f"[agent] api error: {e}")
            return build_card_directly(item, category, price)

        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text")), "")
            try:
                return _extract_json(text)
            except Exception as e:
                print(f"[agent] parse error: {e}")
                return build_card_directly(item, category, price)

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                fn = TOOL_FNS.get(block.name)
                try:
                    result = fn(**block.input) if fn else {"error": f"unknown tool {block.name}"}
                except Exception as e:
                    result = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        break

    return build_card_directly(item, category, price)


# Direct (non-LLM) card builder. Same shape as the agent's output, used as
# the fallback when no API key is configured or the agent call fails.

def _format_short(d: str) -> str:
    return date.fromisoformat(d).strftime("%b %-d") if d else ""


def _format_price(p: float) -> str:
    return f"€{p:.0f}" if p == int(p) else f"€{p:.2f}"


def _format_days(n: int) -> str:
    return "same day" if n == 0 else (f"~{n} day" if n == 1 else f"~{n} days")


def build_card_directly(item: str, category: str, price: float) -> dict:
    fc = ledger.forecast_goal_impact(price)
    baseline = ledger.category_baselines().get(category)
    pattern = _tool_pattern(category)
    carbon = ledger.carbon_for_purchase(price, category)

    ratio_part = ""
    if baseline and baseline > 0:
        ratio = price / baseline
        if ratio >= 1.5 or ratio < 0.7:
            ratio_part = f" · {ratio:.1f}x your usual {category} spend"

    velocity = fc["daily_velocity_eur"]
    days_at_pace = round(price / velocity) if velocity > 0 else 0
    pace = _format_days(days_at_pace) + (" at your pace" if days_at_pace else "")

    if fc["delay_days"] == 0:
        impact_line = f"No shift to {fc['goal_name']} — same day ({_format_short(fc['current_eta'])})"
    else:
        impact_line = (f"Pushes {fc['goal_name']} from {_format_short(fc['current_eta'])} "
                       f"→ {_format_short(fc['new_eta'])}")

    return {
        "headline":     f"{item} — {_format_price(price)}",
        "impact_line":  impact_line,
        "context_line": f"{pace}{ratio_part}",
        "carbon_line":  f"{carbon['kg_co2e']} kg CO2e · {carbon['equivalent']}",
        "footer":       "Your call.",
        "actions": [
            {"label": "Plan it", "action": "draft_transfer"},
            {"label": "Not now", "action": "log_skip"},
        ],
        "_pattern": pattern,
    }


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(build_card_directly("Carhartt jacket", "clothing", 300), indent=2))

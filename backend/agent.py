"""The Horizon agent: vision result + price → Perspective Card payload."""
import json
import os
from dotenv import load_dotenv
from anthropic import Anthropic

from tools import (
    get_savings_velocity,
    get_goal_status,
    get_category_baseline,
    find_personal_pattern,
    forecast_goal_impact,
)

load_dotenv()
client = Anthropic()

def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from Claude's text output.
    Handles markdown fences, prose preambles, and trailing text.
    """
    text = text.strip()

    # Strip markdown fences
    if "```" in text:
        # Get content between first set of fences
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

    # Find the JSON object boundaries — first { to matching last }
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in: {text[:200]}")

    json_str = text[start : end + 1]
    return json.loads(json_str)

TOOL_DEFINITIONS = [
    {
        "name": "get_savings_velocity",
        "description": "Get the user's daily discretionary savings velocity in EUR — how much surplus cash they generate per day, excluding rent, salary, and recurring bills.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_goal_status",
        "description": "Get the user's primary savings goal: name, target amount, and current saved amount.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_category_baseline",
        "description": "Get the user's average single-purchase amount in a given category. Use to compare a new purchase to the user's normal spending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Spending category, e.g. 'clothing', 'electronics', 'food_dining'",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "find_personal_pattern",
        "description": "Find the most relevant behavioral pattern in the user's recent transactions for a given category. Returns frequency_alert (lots of purchases recently), first_in_a_while (long gap), or on_pace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
            },
            "required": ["category"],
        },
    },
    {
        "name": "forecast_goal_impact",
        "description": "Calculate how a new purchase of given price would delay the user's savings goal. Returns current ETA, new ETA, and delay in days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "price_eur": {"type": "number"},
            },
            "required": ["price_eur"],
        },
    },
]


TOOL_FUNCTIONS = {
    "get_savings_velocity": lambda **kw: get_savings_velocity(),
    "get_goal_status": lambda **kw: get_goal_status(),
    "get_category_baseline": lambda **kw: get_category_baseline(**kw),
    "find_personal_pattern": lambda **kw: find_personal_pattern(**kw),
    "forecast_goal_impact": lambda **kw: forecast_goal_impact(**kw),
}


SYSTEM_PROMPT = """You are bunq Horizon, a financial clarity agent for bunq — bank of The Free.

Your job: given an item the user is considering buying (with price), surface the most useful context about its impact on their savings and behavior. You output a Perspective Card.

CORE PRINCIPLES (non-negotiable):
1. Inform, never judge. Show the trade-off; the user decides.
2. Never use "you should" or "you shouldn't". Approved phrases: "your call", "for context", "heads up", "in line with".
3. Short and concrete. The card is 2-3 lines max.
4. Treat the user as a capable adult, not someone who needs protecting.
5. Neutral tone — no emoji, no exclamation marks, no cheerleading.

WORKFLOW:
1. Call forecast_goal_impact with the price → get delay days and date shift.
2. Call find_personal_pattern with the item's category → get a behavioral insight.
3. Call get_category_baseline with the item's category → for the "Nx your usual" comparison.
4. Synthesize into a Perspective Card.

OUTPUT FORMAT:
Your final response MUST be a single raw JSON object and nothing else.
- No preamble like "Here's the card:"
- No markdown code fences
- No explanation after the JSON
- Just the JSON object, starting with { and ending with }

The JSON schema:
{
  "headline": "ITEM_NAME — €PRICE",
  "impact_line": "Pushes [GOAL_NAME] from [OLD_DATE] → [NEW_DATE]",
  "context_line": "~[N] days at your pace · [Nx] your usual [category] spend",
  "footer": "Your call.",
  "actions": [
    {"label": "Plan it", "action": "draft_transfer"},
    {"label": "Not now", "action": "log_skip"}
  ]
}

EXAMPLE OUTPUT for a €300 jacket:
{
  "headline": "Carhartt jacket — €300",
  "impact_line": "Pushes Tokyo 2026 from Aug 4 → Aug 24",
  "context_line": "~20 days at your pace · 2.5x your usual clothing spend",
  "footer": "Your call.",
  "actions": [
    {"label": "Plan it", "action": "draft_transfer"},
    {"label": "Not now", "action": "log_skip"}
  ]
}
"""


def run_agent(item: str, category: str, price: float) -> dict:
    """Vision result + price → Perspective Card payload."""
    user_message = f"""The user is considering buying:
- Item: {item}
- Category: {category}
- Price: €{price}

Use your tools to gather context, then output the Perspective Card JSON."""

    messages = [{"role": "user", "content": user_message}]

    # Loop: agent calls tools until it gives a final answer
    for _ in range(8):  # safety cap on iterations
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            # Extract final JSON from text block
            text = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    text = block.text
                    break

            return _extract_json(text)

        if resp.stop_reason == "tool_use":
            # Run each requested tool, append results, continue loop
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    fn = TOOL_FUNCTIONS[block.name]
                    result = fn(**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        raise RuntimeError(f"Unexpected stop_reason: {resp.stop_reason}")

    raise RuntimeError("Agent exceeded max iterations")


# ---- Test ----
if __name__ == "__main__":
    print("Running agent for: Carhartt WIP Detroit Jacket, clothing, €300")
    print("(this takes ~5-10 seconds — agent is calling tools)")
    print()

    result = run_agent("Carhartt WIP Detroit Jacket", "clothing", 300)
    print(json.dumps(result, indent=2, ensure_ascii=False))
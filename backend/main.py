"""POST /analyze — image + price → Perspective Card.

This is the only endpoint Person C's frontend talks to.
"""
import os
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from vision import analyze_image
from agent import run_agent
from tools import forecast_goal_impact

load_dotenv()

app = FastAPI(title="bunq Horizon — Brain")

# Allow Person C's frontend to call us from any origin (Vercel, localhost, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Sanity check Person C can use to confirm the backend is alive."""
    return {"status": "ok", "demo_mode": _demo_mode_active()}


@app.post("/analyze")
async def analyze(file: UploadFile, price: float = Form(...)):
    """Frontend posts image + price, gets back a Perspective Card.
    
    Request: multipart/form-data
      - file: image bytes (jpeg, png)
      - price: number (as form field)
    
    Returns:
      {
        "vision": { item, category, confidence, brief_description },
        "card":   { headline, impact_line, context_line, footer, actions }
      }
    """

    # ---- Demo mode: return canned response (live-demo Wi-Fi insurance) ----
    if _demo_mode_active():
        return _demo_response(price)

    # ---- Validate input ----
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB cap
        raise HTTPException(413, "Image too large (max 10MB)")
    if len(image_bytes) < 100:
        raise HTTPException(400, "Image is empty or too small")

    # ---- Step 1: Vision ----
    try:
        vision_result = analyze_image(image_bytes)
    except Exception as e:
        print(f"[vision error] {e}")
        vision_result = {"item": "Item", "category": "other", "confidence": "low"}

    if "error" in vision_result:
        vision_result = {
            "item": "Item",
            "category": "other",
            "confidence": "low",
            "brief_description": "Could not identify item",
        }

    item = vision_result.get("item", "Item")
    category = vision_result.get("category", "other")

    # ---- Step 2: Agent ----
    try:
        card = run_agent(item, category, price)
    except Exception as e:
        print(f"[agent error] {e}")
        card = _minimal_fallback(item, price, category)

    return {"vision": vision_result, "card": card}


# ---- Helpers ----

def _demo_mode_active() -> bool:
    return os.getenv("DEMO_MODE", "false").lower() == "true"


def _demo_response(price: float) -> dict:
    """Canned response — used during the live demo if Wi-Fi or APIs fail."""
    return {
        "vision": {
            "item": "Carhartt WIP Detroit Jacket",
            "category": "clothing",
            "confidence": "high",
            "brief_description": "Brown canvas work jacket",
        },
        "card": {
            "headline": f"Carhartt jacket — €{price:.0f}",
            "impact_line": "Pushes Tokyo 2026 from Aug 4 → Aug 24",
            "context_line": "~20 days at your pace · 2.5x your usual clothing spend",
            "footer": "Your call.",
            "actions": [
                {"label": "Plan it", "action": "draft_transfer"},
                {"label": "Not now", "action": "log_skip"},
            ],
        },
    }


def _minimal_fallback(item: str, price: float, category: str) -> dict:
    """If the agent crashes mid-flight, build a card from raw math (no LLM)."""
    fc = forecast_goal_impact(price)
    return {
        "headline": f"{item} — €{price:.0f}",
        "impact_line": f"Pushes {fc['goal_name']} from {fc['current_eta']} → {fc['new_eta']}",
        "context_line": f"~{fc['delay_days']} days at your pace",
        "footer": "Your call.",
        "actions": [
            {"label": "Plan it", "action": "draft_transfer"},
            {"label": "Not now", "action": "log_skip"},
        ],
    }
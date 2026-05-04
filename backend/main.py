# bunq Horizon backend. /analyze is the main path, the rest are pieces of it.
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import ledger
from agent import build_card_directly, run_agent
from vision import CATEGORIES, analyze_image

load_dotenv()

app = FastAPI(title="bunq Horizon", version="1.0.0")

# wide-open CORS, fine for the demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


def _claude_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def _demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").lower() == "true"


@app.get("/health")
def health():
    return {
        "ok": True,
        "claude_enabled": _claude_enabled(),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "demo_mode": _demo_mode(),
    }


@app.get("/context")
def context():
    data = ledger.load_ledger()
    velocity = ledger.daily_velocity()
    return {
        "goal":        ledger.goal_status(),
        "velocity":    velocity,
        "baselines":   ledger.category_baselines(),
        "categories":  CATEGORIES,
        "source":      data.get("source", "cached"),
    }


@app.get("/balance")
def balance():
    data = ledger.load_ledger()
    txns = data["transactions"]
    starting = data.get("starting_balance_eur", 0.0)
    current = round(starting + sum(t["amount"] for t in txns), 2)
    recent = sorted(txns, key=lambda t: t["date"], reverse=True)[:10]
    return {
        "source": data.get("source", "cached"),
        "balance_eur": current,
        "recent_payments": recent,
        "user_id": data.get("user_id"),
        "account_id": data.get("account_id"),
    }


class ClassifyOut(BaseModel):
    item: str
    category: str
    confidence: str
    brief_description: Optional[str] = None
    source: Optional[str] = None


@app.post("/classify", response_model=ClassifyOut)
async def classify(image: UploadFile = File(...)):
    payload = await image.read()
    if not payload:
        raise HTTPException(400, "empty image")
    return analyze_image(payload, image.content_type or "image/jpeg", image.filename)


# used when the frontend already has a classification and just wants the card
class PerspectiveIn(BaseModel):
    price: float = Field(..., gt=0)
    category: str
    item: Optional[str] = None


@app.post("/perspective")
def perspective(req: PerspectiveIn):
    cat = req.category if req.category in CATEGORIES else "other"
    item = req.item or cat
    return build_card_directly(item, cat, req.price)


# canned response for the case where vision is acting up
DEMO_CARD = {
    "vision": {
        "item": "Carhartt WIP Detroit Jacket",
        "category": "clothing",
        "confidence": "high",
        "brief_description": "Brown canvas work jacket",
        "source": "demo",
    },
}


@app.post("/analyze")
async def analyze(image: UploadFile = File(...), price: float = Form(...)):
    if price <= 0:
        raise HTTPException(400, "price must be > 0")

    payload = await image.read()
    if not payload:
        raise HTTPException(400, "empty image")
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "image too large (max 10 MB)")

    if _demo_mode():
        v = DEMO_CARD["vision"]
        return {"vision": v, "card": run_agent(v["item"], v["category"], price)}

    vision = analyze_image(payload, image.content_type or "image/jpeg", image.filename)
    item = vision.get("item", "Item")
    category = vision.get("category", "other")
    if category not in CATEGORIES:
        category = "other"

    try:
        card = run_agent(item, category, price)
    except Exception as e:
        print(f"[analyze] agent died, falling back: {e}")
        card = build_card_directly(item, category, price)

    return {"vision": vision, "card": card}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)

# bunq Horizon

> Snap a photo of any item. See how many days it pushes back your savings goal — and what it costs the planet.

A multimodal AI feature for bunq that turns abstract financial decisions into concrete future-self ones. Submitted to bunq Hackathon 7.0.

**Example:** Photo of a jacket → type `€300` → *"Pushes your Tokyo 2026 goal from Aug 4 → Aug 24. ~6 days at your pace · 2.5x your usual clothing spend. 120 kg CO₂e ≈ 670 km of driving. Your call."*

## Tech highlights

- **Multimodal vision** — Claude Sonnet 4.6 classifies arbitrary product photos into one of nine spend categories with structured-output JSON
- **Agentic tool use** — Claude calls six custom tools (`get_savings_velocity`, `forecast_goal_impact`, `estimate_carbon`, …) that derive every number from the actual ledger; the model never makes up figures
- **Signed bunq sandbox client** — full RSA handshake (installation → device-server → session-server) with persisted device tokens and PKCS#1 v1.5 request signing, written from scratch
- **Three-layer fallback ladder** — live bunq → cached snapshot → frontend-local compute, so the demo runs end-to-end even without internet or API keys
- **Pinned dependencies, deploys clean** — `requirements.txt` and `package-lock.json` lock everything to known-working versions; one-click deploy via `render.yaml` + Vercel

## Try it locally (60 seconds)

You'll need Python 3.10+ and Node 18+.

**Backend** (one terminal):
```
git clone https://github.com/emrewhiting/bunq-horizon.git
cd bunq-horizon/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

**Frontend** (second terminal):
```
cd bunq-horizon/frontend
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:5173`.

> **No Anthropic key needed to try the flow.** Without one, the vision step falls back to a filename classifier — name your test image `jacket.jpg` or `coffee.jpg` and the rest of the pipeline (savings forecast, carbon, the whole card) runs identically. Drop a real key in `backend/.env` if you want true vision.

## How the perspective is computed

Three numbers feed every result, all derived from the ledger in `backend/bunq_data.json`:

```
daily_velocity   = (income − outflow) / 30 days
goal_eta         = today + remaining_to_goal / daily_velocity
category_avg     = mean(price) for prior purchases in that category
```

- **Delay** = `ceil(price / daily_velocity)` days
- **Ratio** = `price / category_avg` (only shown if it's notably high or low)
- **Carbon** = `price × category_factor`, mapped to a relatable equivalent (km of driving, beef burgers, tree-years)

Carbon factors are order-of-magnitude estimates from EU Exiobase / WWF lifestyle calculator ranges — defensible for a demo, not a peer-reviewed model.

## Architecture

```
frontend (React + Vite, Tailwind)
   │
   ├─ /classify    image → vision (item + category)
   ├─ /perspective price + category → Perspective Card
   └─ /analyze     image + price → both, in one call
   │
backend (FastAPI)
   ├─ vision.py        → Anthropic multimodal
   ├─ agent.py         → Claude tool-use loop, builds the card
   ├─ ledger.py        → derives velocity, baselines, ETAs, carbon
   └─ bunq_client.py   → signed sandbox API client
```

## API endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ok, claude_enabled, model}` |
| GET | `/context` | — | goal + averages + categories |
| GET | `/balance` | — | live bunq balance + recent payments (or cached fallback) |
| POST | `/classify` | multipart `image` | `{item, category, confidence, source}` |
| POST | `/perspective` | `{price, category, item?}` | full perspective payload |
| POST | `/analyze` | multipart `image` + `price` | classification + perspective in one call |

## Deploying

**Backend → Render** (free tier): push to GitHub → New + → Blueprint → pick the repo (it auto-detects `render.yaml`) → set `ANTHROPIC_API_KEY` and `BUNQ_API_KEY` env vars → done.

**Frontend → Vercel**: New Project → import the repo → Root directory: `frontend` → set `VITE_API_URL` to your Render URL → deploy.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite + Tailwind |
| Backend | FastAPI (Python 3.10+) |
| Vision | Claude Sonnet 4.6 (multimodal) |
| Agent | Claude tool-use loop |
| Bank data | bunq sandbox API (live) + cached JSON (fallback) |
| Carbon | Category emission factors (kg CO₂e per €) |

## Credits

- bunq sandbox: [doc.bunq.com](https://doc.bunq.com/)
- bunq API client adapted from [this PSD2 reference implementation](https://github.com/two-trick-pony-NL/PSD2-Implementation-for-bunq-API)
- Carbon factors: WWF + EU Exiobase ranges

## License

MIT — see [LICENSE](./LICENSE).

## Notes

Personal submission for bunq Hackathon 7.0. The cached `bunq_data.json` is
fully synthetic (zeroed IDs, made-up transactions). No bunq-internal data,
keys, or hackathon-confidential material ships with this repo. Bring your
own keys to run it.

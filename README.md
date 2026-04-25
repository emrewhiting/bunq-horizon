# bunq Horizon

> Snap a photo of any item. See how many days it pushes back your savings goal — and what it costs the planet.

A multimodal AI feature for bunq that turns abstract financial decisions into concrete future-self ones. Built for the bunq Hackathon 7.0.

## What it does

1. **Take a photo** of something you're thinking of buying
2. **Claude Sonnet vision** identifies the item + category
3. **You confirm the price** (and category, if Claude got it wrong)
4. **The card shows you**: how many days it delays your Tokyo 2026 goal, how it stacks up against your usual spend in that category, and the embodied carbon footprint with a relatable comparison

> Example: "This jacket: €300 — pushes your Tokyo goal from Aug 4 → Aug 24. 20 days. 2.5× your usual clothing spend. 120 kg CO₂e — that's ~670 km of driving. Your call."

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite |
| Backend | FastAPI (Python 3.11) |
| Vision | Claude Sonnet 4.5 |
| Bank data | bunq sandbox API (hybrid, with cached JSON fallback) |
| Carbon model | Category emission factors (kg CO₂e per €) |

## Repo layout

```
.
├── backend/              # FastAPI app
│   ├── main.py           # endpoints + perspective math
│   ├── bunq_client.py    # sandbox auth + payments
│   ├── bunq_data.json    # cached snapshot (goal, velocity, category averages)
│   ├── requirements.txt
│   ├── Procfile          # for Railway / Render
│   └── .env.example
├── frontend/             # Vite + React
│   ├── src/
│   │   ├── App.jsx       # 3 screens: upload → price → result
│   │   ├── api.js
│   │   └── App.css
│   ├── package.json
│   └── vercel.json
├── data/                 # one-off scripts (seed, top-up)
├── render.yaml           # backend deploy config
└── README.md
```

## Local quick start

You'll need Python 3.11+ and Node 18+.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — paste your ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8000
```

Sanity check:
```bash
curl http://localhost:8000/health
# {"ok": true, "claude_enabled": true, "model": "claude-sonnet-4-5-20250929"}
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # leave default if backend is on :8000
npm run dev
```

Open http://localhost:5173.

## Deploying

### Backend → Render (free tier)

1. Push this repo to GitHub
2. Render → New + → **Blueprint** → pick the repo (it auto-detects `render.yaml`)
3. Add `ANTHROPIC_API_KEY` and `BUNQ_API_KEY` as environment variables in the Render dashboard
4. Wait ~2 min for build → copy your `https://bunq-horizon-api-xxx.onrender.com` URL

### Frontend → Vercel

1. Vercel → New Project → import this repo
2. **Root directory**: `frontend`
3. Framework: Vite (auto-detected)
4. Add env var `VITE_API_URL` = the Render URL from above
5. Deploy

## How the math works

Three numbers feed every result, all sourced from `backend/bunq_data.json`:

```
daily_velocity   = €15/day saved toward goal
goal_date        = 2026-08-04
category_avgs    = clothing €120, food €25, transport €41.50, entertainment €36
```

- **Delay** = `ceil(price / daily_velocity)` days
- **Ratio** = `price / category_avg`
- **Carbon** = `price × category_factor` (factors below)

### Category emission factors (kg CO₂e per €1)

| Category | Factor | Source |
|---|---|---|
| clothing | 0.40 | Fast fashion textile chains |
| food | 0.18 | Mixed groceries + dine-in |
| transport | 0.45 | Mostly fuel/airfare |
| entertainment | 0.10 | Subscriptions, low-emission |
| electronics | 0.55 | Manufacturing-heavy |
| home | 0.30 | |
| beauty | 0.25 | |
| other | 0.20 | |

These are order-of-magnitude figures derived from EU Exiobase / WWF lifestyle calculator ranges — defensible for a demo, not a peer-reviewed model.

### Carbon equivalents

We translate kg CO₂e into something visceral:

| If kg CO₂e is… | We show… |
|---|---|
| < 5 | "X beef burgers worth of CO2" |
| 5–30 | "X km of driving" |
| > 30 | "X days of a tree's CO2 absorption" |

## API endpoints

All endpoints are CORS-open for the demo.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ok, claude_enabled, model}` |
| GET | `/context` | — | goal + averages + categories |
| GET | `/balance` | — | live bunq balance + recent payments (or cached fallback) |
| POST | `/classify` | multipart `image` | `{item, category, confidence, source}` |
| POST | `/perspective` | `{price, category, item?}` | full perspective payload |
| POST | `/analyze` | multipart `image` + `price` | classification + perspective in one call |

## Fallback ladder (so the demo never crashes)

The brief says "if anything breaks, hardcode everything." Here's the fallback ladder:

1. **Claude vision fails or no API key** → keyword classifier on filename
2. **bunq sandbox unreachable** → cached `bunq_data.json` snapshot
3. **Backend unreachable from frontend** → frontend computes perspective locally using the same formulas

Result: even with no internet, the demo still runs end-to-end (you'd just lose AI item recognition).

## Demo script (2-3 min)

1. *Hook* — "What if your bank could show you what a purchase really costs your future self?" (10s)
2. Open the app on phone, snap a photo of a coat in a store window (15s)
3. Type €300 → tap "See impact" (10s)
4. Read the card aloud: 20-day delay, 2.5× usual clothing spend, 120 kg CO₂e ≈ 670 km of driving (30s)
5. Tap "I'll skip it" → reset → snap a coffee → €4.50 → tiny delay, "you're fine, treat yourself" (20s)
6. *Why it matters* — bunq already has the data; this turns it into a moment of clarity right when it counts. (30s)

## Credits

- bunq sandbox: [doc.bunq.com](https://doc.bunq.com/)
- API client lifted from [PSD2 reference implementation](https://github.com/two-trick-pony-NL/PSD2-Implementation-for-bunq-API)
- Carbon factors: WWF + EU Exiobase order-of-magnitude ranges

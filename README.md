# TripPilot

An AI travel booking assistant that handles **any** travel request — a flight only, a
hotel tonight, car hire, a transfer, an eSIM, insurance, or a whole trip — and earns
**affiliate commission** when people book through its links.

```
User (web app / Telegram)
   │
   ▼
FastAPI  ──►  AI agent (Claude, tool calling)
   │             ├─ resolve_place       city → IATA code
   │             ├─ search_flights      Travelpayouts / Aviasales fares
   │             ├─ search_hotels       Booking.com search (hotel API slot ready)
   │             ├─ get_extra_links     car, transfer, eSIM, insurance, tours
   │             └─ create_price_alert
   │
   ├─ Every partner link becomes /go/<id>  ──► click recorded ──► 302 to partner
   ├─ Database: chats, links, clicks, trips, price alerts
   └─ Price-alert job (cron) ──► webhook ──► email / SMS
```

## Features

- **One chat box for every travel need.** The agent works out what was asked and only
  searches for that — a flight-only question gets flights, not a holiday plan.
- **Result cards with Book buttons.** Flights show best value first; hotels show a live
  search link (real hotel cards once a hotel API is connected).
- **Never invents prices.** The agent may only show what partner APIs return.
- **Click tracking.** Each link shown gets an id; `/go/<id>` logs the click and redirects
  to the partner with your affiliate id. `/api/admin/stats` shows links shown, clicks and
  click rate per category.
- **Trip wallet.** Save results, mark them booked, remove them.
- **Price alerts.** Created from the app or by asking in chat; a scheduled job checks
  fares and calls your webhook when a target is hit.
- **Telegram bot** using the same agent.
- **Commission disclosure** shown with results, and links marked `rel="sponsored"`.

## Quick start (local)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env          # add your keys (see below)
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. API docs: <http://localhost:8000/docs>.
`/api/health` shows which partners are configured.

Run the tests (no keys needed — the AI and partners are faked):

```bash
cd backend && pytest
```

### With Docker + Postgres

```bash
cp .env.example backend/.env     # add your keys
docker compose up --build
```

## Keys you need

| Setting | Where to get it | Needed for |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Chat (required) |
| `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER` | travelpayouts.com → Tools → API | Flight search + flight commission |
| `BOOKING_AID` | Booking.com Affiliate Partner programme | Hotel commission |
| `*_AFFILIATE_URL` | Each program (many are inside Travelpayouts) | Car, transfer, eSIM, insurance, tours |
| `ADMIN_TOKEN` | Any long random string | `/api/admin/stats` |
| `ALERT_WEBHOOK_URL` | Zapier / Make / n8n webhook | Price-alert emails |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | @BotFather | Telegram bot |

Anything not set is simply switched off; the agent tells the user that a service isn't
available instead of making something up.

## Deploying

Any host that runs a Docker image works (Render, Railway, Fly.io, a VPS):

1. Deploy the `Dockerfile`. It listens on `$PORT` (default 8000).
2. Add a Postgres database and set `DATABASE_URL` (`postgresql+psycopg://...`).
3. Set `PUBLIC_BASE_URL` to your public https address (used in tracked links).
4. Add the keys above.
5. Schedule the price-alert check, e.g. every 6 hours:
   `cd /srv/backend && python -m app.jobs.price_alerts`
6. Telegram (optional): register the webhook once —
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook" -d url=<PUBLIC_BASE_URL>/api/telegram/webhook -d secret_token=<SECRET>`

Tables are created automatically on start. For schema changes later, add Alembic.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | `{message, session_id?}` → `{reply, session_id, cards}` |
| GET | `/go/{id}` | Tracked redirect to partner |
| GET/POST | `/api/trips` | List / create trips |
| POST | `/api/trips/quick-save` | Save a result to the latest trip |
| PATCH/DELETE | `/api/trips/items/{id}` | Mark booked / remove |
| GET/POST/DELETE | `/api/alerts` | Price alerts |
| GET | `/api/admin/stats?days=30` | Clicks by category (Bearer `ADMIN_TOKEN`) |
| POST | `/api/telegram/webhook` | Telegram updates |

User-scoped endpoints need an `X-Device-Id` header (the web app sends a random id it
keeps in the browser). Add real accounts before storing anything sensitive.

## Project layout

```
backend/app/
  main.py               app setup, serves ../frontend
  config.py, db.py, models.py, schemas.py, deps.py
  agent/                prompts, tools (+ link tracking), agent loop, LLM wrapper
  providers/            places, flights, hotels, extras, TTL cache
  routers/              chat, go, trips, alerts, admin, telegram
  services/             shared chat logic, alert notifications
  jobs/price_alerts.py  scheduled fare checks
backend/tests/          pytest suite with a fake LLM
frontend/               web app (no build step): index.html, app.js, styles.css
```

## Roadmap

- **Live flight prices:** current fares come from the Data API cache. Apply for the
  real-time Aviasales or Kiwi.com search API once you have traffic; only
  `providers/flights.py` changes.
- **Real hotel list:** implement `_search_hotel_api` in `providers/hotels.py` when
  approved for a hotel API (Booking Demand API, Expedia Rapid, Agoda).
- User accounts and login; Redis for cache and rate limiting; WhatsApp channel;
  SEO landing pages (e.g. "cheapest time to fly Perth to Bali").

## Compliance

- Keep the affiliate disclosure visible (ACCC in Australia, FTC in the US, CMA in the UK).
- Follow each program's terms (e.g. rules on caching prices or bidding on brand names).
- Add a privacy policy before launch; chats and alert emails are stored in your database.

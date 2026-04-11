# ZTA Frontend (Next.js)

**Plan Alignment:** Frontend behavior and roadmap are governed by `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). This file remains implementation-focused; plan requirements take precedence. See `docs/PLAN_ALIGNMENT.md`.

Next.js command console for the ZTA-AI backend.

## Features

- Role-based mock login using seeded personas (`mock:<email>`)
- Dedicated demo routes:
	- `/chat` for conversational workspace
	- `/monitor` for pipeline telemetry and stage feed
	- `/admin` for admin controls and snapshots
- WebSocket chat streaming (`/chat/stream`)
- Real-time pipeline monitor (`/admin/pipeline/monitor`)
- Admin dashboard (users, policies, data sources, audit view, kill switch)
- Session persistence for API base URL and token/user state

## Local Development

From repository root:

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000 (redirects to `/chat`)

Demo pages:

- http://localhost:3000/chat
- http://localhost:3000/monitor
- http://localhost:3000/admin

Backend expected at: http://localhost:8000

You can override API base from the UI, or define:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Quality Checks

```bash
npm run lint
npm run build
```

## Docker

The root compose files build this frontend and expose it on:

- http://localhost:8080

This uses a standalone Next.js production container (`frontend/Dockerfile`).

## Legacy Static UI

Previous static assets are retained in `frontend/legacy-static/` for reference only and are excluded from linting.

Copy/paste this as your first message when starting a new Claude Code session:

---

I'm continuing work on the Swing Doctor golf analytics platform (~/golf-sim/). Here's where we left off:

## What's Built

**PWA (public/index.html)** — live at swing.doctor:
- Full dashboard: KPIs, charts, yardage map, dispersion, session history
- AI Coach tab with local analysis: handicap estimation, per-club insights (spin, launch, path/face combo, dispersion, miss pattern), targeted drills, equipment notes, next session plan
- Cloud auth UI in Profile tab (sign up/sign in — needs backend deployed)
- API client object (API.*) with auth, sessions, analytics, AI, billing
- Multiple profiles, light/dark mode, hard refresh, CSV import

**Backend (backend/)** — FastAPI + PostgreSQL + Redis:
- Auth: register, login, refresh, email verify, password reset (JWT + bcrypt)
- Profiles: CRUD with clubs, subscription tier limits
- Sessions: CSV upload with auto-detect (3 Bushnell/Foresight parsers), pagination
- Analytics engine: club summaries, session trends, improvement tracking, handicap estimation — 5 API endpoints
- AI swing analysis: Claude-powered coaching via POST /ai/profiles/{id}/analyze
- Stripe billing: checkout, portal, webhooks for subscription lifecycle
- Email service: verification + password reset with SMTP
- Alembic migration, Docker compose, 56 passing parser tests
- Fly.io deploy config ready (fly.toml + DEPLOY.md)
- GitHub Actions CI pipeline

**Brand messaging:**
- Headline: "Golf is hard enough without the guesswork."
- Tagline: "Stop guessing. Start improving."
- Product line: "Your data should coach you."

## What's Next (pick one or tell me what to focus on)

1. Deploy backend to Fly.io (need flyctl installed + Stripe/Anthropic API keys)
2. Build landing page for swing.doctor (marketing site)
3. Add session comparison feature (compare two sessions side by side)
4. Add data export (PDF report / CSV download)
5. Keep enhancing the local AI coach
6. Wire more PWA features to the backend API

The repo is at ~/golf-sim/, GitHub at sgrutsch-hub/g730. Backend requires Python 3.11+ (system Python is 3.9 — parser tests work, API tests need Docker or 3.11+).

# Deploying Swing Doctor API

## Prerequisites

- [flyctl CLI](https://fly.io/docs/flyctl/install/) installed (`brew install flyctl`)
- Fly.io account (`fly auth signup` or `fly auth login`)
- GitHub repo with `FLY_API_TOKEN` secret configured for CI/CD

## First-time setup

```bash
cd backend

# Login to Fly.io
fly auth login

# Create the app
fly apps create swing-doctor-api

# Create Postgres database
fly postgres create --name swing-doctor-db --region ord
fly postgres attach swing-doctor-db --app swing-doctor-api
# This automatically sets DATABASE_URL as a secret

# Create persistent volume for file storage
fly volumes create swing_doctor_data --region ord --size 1

# Create Redis (Upstash via Fly.io)
fly redis create --name swing-doctor-redis --region ord
# Note the REDIS_URL from the output

# Set all required secrets
fly secrets set \
  REDIS_URL="redis://..." \
  JWT_SECRET="$(openssl rand -hex 32)" \
  ANTHROPIC_API_KEY="sk-ant-..." \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  ADMIN_PASSWORD="<choose-a-strong-password>"

# Deploy
fly deploy
```

### Required secrets reference

| Secret                 | Description                              |
| ---------------------- | ---------------------------------------- |
| `DATABASE_URL`         | Set automatically by `fly postgres attach` |
| `REDIS_URL`            | Redis connection string                  |
| `JWT_SECRET`           | 256-bit hex key for JWT signing          |
| `ANTHROPIC_API_KEY`    | Claude API key for AI coaching           |
| `STRIPE_SECRET_KEY`    | Stripe live/test secret key              |
| `STRIPE_WEBHOOK_SECRET`| Stripe webhook signing secret            |
| `ADMIN_PASSWORD`       | Admin account password                   |

## Running migrations

Migrations run automatically on deploy (the Dockerfile CMD runs `alembic upgrade head` before starting uvicorn). To run manually:

```bash
# SSH into the running machine
fly ssh console

# Inside the container
cd /app
alembic upgrade head

# Or run a specific migration
alembic upgrade +1
alembic downgrade -1
```

## Seeding the admin account

```bash
# SSH into the machine and run the seed script
fly ssh console -C "python -m app.scripts.seed_admin"

# Or via the API if an admin creation endpoint exists
curl -X POST https://swing-doctor-api.fly.dev/api/admin/setup \
  -H "Content-Type: application/json" \
  -d '{"password": "<ADMIN_PASSWORD>"}'
```

## Checking logs

```bash
# Tail live logs
fly logs

# Filter by level
fly logs --level error

# Logs from a specific machine
fly logs --instance <instance-id>
```

## Scaling

```bash
# Horizontal: add more machines
fly scale count 2

# Vertical: increase memory/CPU
fly scale vm shared-cpu-1x --memory 1024

# Check current scale
fly scale show

# Check app status
fly status
```

## Subsequent deploys

Pushing to `main` with changes in `backend/` triggers automatic deployment via GitHub Actions. To deploy manually:

```bash
cd backend
fly deploy
```

## Custom domain

```bash
fly certs add api.swing.doctor
```

Then add a CNAME record in your DNS provider:
- `api` -> `swing-doctor-api.fly.dev`

## Useful commands

```bash
fly status                  # App status and machine list
fly ssh console             # SSH into the container
fly postgres connect        # Connect to Postgres REPL
fly secrets list            # List configured secrets
fly volumes list            # List persistent volumes
fly checks list             # Health check status
```

## Local Development

```bash
cd backend
cp .env.example .env        # Edit with your local values
docker compose up -d        # Start Postgres + Redis + API
docker compose logs -f api  # Watch API logs
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

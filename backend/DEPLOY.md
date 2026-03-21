# Deploying Swing Doctor API

## Fly.io (Recommended)

### First-time setup

```bash
# Install Fly CLI
brew install flyctl

# Login
fly auth login

# Create the app
cd backend
fly apps create swingdoctor-api

# Create Postgres database (free tier: 256MB)
fly postgres create --name swingdoctor-db --region ord
fly postgres attach swingdoctor-db --app swingdoctor-api

# Set secrets (Fly sets DATABASE_URL automatically from postgres attach)
fly secrets set \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  STRIPE_PRICE_PRO_MONTHLY="price_..." \
  STRIPE_PRICE_PRO_YEARLY="price_..." \
  STRIPE_PRICE_PRO_PLUS_MONTHLY="price_..." \
  STRIPE_PRICE_PRO_PLUS_YEARLY="price_..." \
  ANTHROPIC_API_KEY="sk-ant-..." \
  SMTP_HOST="smtp.gmail.com" \
  SMTP_PORT="587" \
  SMTP_USER="..." \
  SMTP_PASSWORD="..." \
  EMAIL_FROM="noreply@swing.doctor"

# Deploy
fly deploy
```

### Subsequent deploys

```bash
cd backend
fly deploy
```

### Useful commands

```bash
fly logs                    # Tail logs
fly ssh console             # SSH into the container
fly postgres connect        # Connect to Postgres
fly status                  # App status
fly scale count 1           # Scale to 1 machine
fly secrets list            # List configured secrets
```

### Custom domain

```bash
fly certs add api.swing.doctor
```

Then add a CNAME record in Cloudflare:
- `api` → `swingdoctor-api.fly.dev`

## Local Development

```bash
cd backend
cp .env.example .env
# Edit .env with your values

docker compose up -d        # Start Postgres + Redis + API
docker compose logs -f api  # Watch API logs
```

API will be at http://localhost:8000
Docs at http://localhost:8000/docs

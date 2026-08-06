# Deploying to a single server

> **Prefer a click-through walkthrough?** [`deploy/deploy-guide.html`](deploy/deploy-guide.html)
> is a first-timer's visual version of everything below — open it in a browser. This file
> is the reference; that one holds your hand through renting the box, DNS, and HTTPS.

This is the launch setup: one Ubuntu box running the whole stack in Docker —
PostgreSQL, Redis, a Celery worker, the Django app under gunicorn, and Caddy in
front for automatic HTTPS. It suits the first handful of schools and costs about
USD 10–20 a month. When you outgrow one box, the same images move to managed
Postgres and a container service (see *Scaling out* at the end).

## What you need

- A server: any provider's small Ubuntu 22.04+ VPS with ~2 GB RAM. Hetzner,
  DigitalOcean, Linode, or **AWS Lightsail in `af-south-1`** (Cape Town) for the
  lowest latency to Kenya.
- A domain name, pointed at the server (an `A` record → the server's IP). You can
  do the first boot without one over plain HTTP, then add it.

## First deploy

```bash
# 1. On the server, install Docker Engine + the compose plugin.
curl -fsSL https://get.docker.com | sh

# 2. Get the code.
git clone https://github.com/Giddymaster/CBC.git
cd CBC

# 3. Configure. Fill in SECRET_KEY, SITE_ADDRESS, ALLOWED_HOSTS, and the DB password.
cp deploy/.env.prod.example deploy/.env.prod
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # -> SECRET_KEY
nano deploy/.env.prod

# 4. Build and start everything.
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build

# 5. Create the database schema.
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod \
    run --rm web python manage.py migrate

# 6. Create YOUR operator account (the platform owner, above all schools).
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod \
    run --rm web python manage.py createsuperuser
#    Leave the school blank — an operator belongs to no school.
```

Open `https://your-domain`. Caddy fetches the HTTPS certificate on first request;
give it a few seconds. Sign in as the operator and register your first school
from the operator console.

> **Smoke test before DNS?** Set `SITE_ADDRESS=:80` and `SECURE_SSL_REDIRECT=false`
> in `deploy/.env.prod`, bring the stack up, and open `http://SERVER-IP`. Switch
> both back once the domain resolves.

## Optional seed data

To explore with the demo school and a sample curriculum (never on a real
tenant's server):

```bash
docker compose ... run --rm web python manage.py seed_demo
docker compose ... run --rm web python manage.py seed_curriculum
```

## Updating to a new release

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod \
    run --rm web python manage.py migrate
```

The frontend is rebuilt into the Caddy image, so `up --build` ships new UI too.

## Backups — do this before you have real schools

Everything durable is in two Docker volumes: `cbc_pgdata` (the database) and
`cbc_media` (learner photos, report-card PDFs). Back both up on a schedule.

```bash
# Database — a compressed SQL dump.
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod \
    exec -T db pg_dump -U cbc cbc | gzip > cbc-$(date +%F).sql.gz

# Media — a tarball of the volume.
docker run --rm -v cbc_media:/m -v "$PWD":/out alpine \
    tar czf /out/media-$(date +%F).tar.gz -C /m .
```

Copy both off the server (object storage, another host). A school's records are
minors' data — losing them is not an option, and the Kenya DPA 2019 obliges you
to protect them.

## Watching it

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod ps
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f web
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f caddy
```

## Before you take real money and real learner data

- **Register your business** and put up terms of service.
- **Kenya DPA 2019:** you are the *data processor*; each school is a *controller*.
  Register with the ODPC and sign a data-processing agreement with each school.
- **Firewall:** allow only 80, 443, and your SSH port.
- **Automate backups** (above) and test a restore once.
- Point `DARAJA_CALLBACK_URL` at `https://your-domain/api/payments/stk-callback/`
  and register the C2B confirmation URL on your paybill, when you go live on
  M-Pesa.

## Scaling out (later, not now)

The single box holds a lot of schools before it strains. When it does: move the
database to managed PostgreSQL (RDS in `af-south-1`), move `media` to S3-compatible
object storage, and run `web`/`worker` as multiple containers behind a load
balancer. The images built here are the same ones you would deploy there — only
the database host, the media backend, and the number of replicas change.

# Deploying Mitra

One environment = one server running `compose.yml`: Caddy (HTTPS), Postgres, migrations, the
core API, the scheduler, the owner app, the marketing site and the voice service. Staging, demo
and production are separate servers with separate databases, keys and env files.

| Host (staging) | What |
|---|---|
| `staging.viduronai.in` | owner app |
| `api.staging.viduronai.in` | core API (webhooks land here; `/internal/*` is blocked) |
| `site.staging.viduronai.in` | marketing site |
| `voice.staging.viduronai.in` | voice service (test page, carrier media) |

Images are built by GitHub Actions (`.github/workflows/deploy.yml`) and pulled by the server;
nothing is built on the server. A push to `main` runs CI and then deploys to staging.

## First-time setup (staging)

1. **Server.** AWS Lightsail, region Mumbai (`ap-south-1`), Ubuntu 24.04, 4 GB plan. Attach a
   static IP. Networking tab: allow TCP 22 (your IP only), TCP 80, TCP 443, UDP 443,
   UDP 10000-65535. Turn on automatic snapshots.
2. **DNS** (GoDaddy, `viduronai.in`): A records `staging` and `*.staging` -> the static IP.
3. **Bootstrap.** Copy `deploy/server-setup.sh` to the server and run `bash server-setup.sh`.
4. **Deploy key.** On your laptop: `ssh-keygen -t ed25519 -f mitra-staging-deploy -N ""`.
   Put the `.pub` line in `/home/deploy/.ssh/authorized_keys` on the server.
5. **Secrets on the server** (as `deploy`, in `/opt/mitra`): copy `deploy/.env.example` to
   `.env`, `deploy/env/core.env.example` to `env/core.env`, `deploy/env/voice.env.example` to
   `env/voice.env`, and fill them in (`openssl rand -base64 36` for each secret; every
   environment gets its own). `chmod 600 .env env/*.env`.
6. **Phone-encryption key** (`MITRA_PHONE_ENC_KEY_KMS`): create a KMS key `alias/mitra-staging`
   in ap-south-1 and an IAM user allowed `kms:Decrypt` and `kms:GenerateDataKeyWithoutPlaintext`
   on it only; put its access keys in `env/core.env`. After the first image pull:
   `docker compose --env-file .env run --rm core python -m mitra_core.keystore new-kms-key --key-id alias/mitra-staging`
   and paste the output into `MITRA_PHONE_ENC_KEY_KMS`. Never change it once numbers exist.
7. **GitHub** (Settings > Environments > `staging`): variable `DOMAIN=staging.viduronai.in`;
   secrets `SSH_HOST` (static IP), `SSH_KEY` (the private key from step 4), `SSH_KNOWN_HOSTS`
   (`ssh-keyscan <static IP>`).
8. **Deploy.** Push to `main` (or Actions > Deploy > Run workflow). The run ends with a smoke
   test of the API, the app and the site.

Demo and production repeat these steps on their own server with `MITRA_DOMAIN` set to
`demo.viduronai.in` / `app.viduronai.in`, `MITRA_NOINDEX=false` for production only,
`MITRA_SHOW_DEV_OTP=0`, `MITRA_OTP_SHOW_CODE` unset, real providers, and required reviewers on
the GitHub environment so every deploy waits for approval.

## Day to day

- Logs: `docker compose --env-file .env logs -f core scheduler`
- Status: `docker compose --env-file .env ps`
- Roll back: in `/opt/mitra/.env` set `MITRA_TAG` to the previous `<commit sha>-staging` (every
  image stays in GitHub Packages), then `docker compose --env-file .env up -d`. Migrations are
  not undone, so keep them backward compatible (add columns; drop them a release later).
- Backups: nightly at 02:30 IST into `/opt/mitra/backups` (14 days); restore steps are in
  `backup.sh`. Lightsail snapshots cover the whole disk.

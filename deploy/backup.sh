#!/usr/bin/env bash
# Nightly Postgres backup (cron from server-setup.sh). Keeps 14 days in /opt/mitra/backups.
# Restore:  gunzip -c <file>.sql.gz | docker compose exec -T postgres psql -U mitra -d mitra
# Lightsail's automatic daily snapshots cover the whole disk on top of this.
set -euo pipefail
cd /opt/mitra
stamp=$(date +%Y-%m-%d_%H%M)
out="backups/mitra_${stamp}.sql.gz"
docker compose --env-file .env exec -T postgres pg_dump -U mitra -d mitra --no-owner | gzip > "$out.part"
mv "$out.part" "$out"
chmod 600 "$out"
find backups -name 'mitra_*.sql.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: $out ($(du -h "$out" | cut -f1))"

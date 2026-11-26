#!/usr/bin/env bash
set -euo pipefail

# Back up the PostgreSQL database used by the production stack.
# Usage: ./scripts/backup.sh [output_dir]

OUTPUT_DIR="${1:-./backups}"
mkdir -p "$OUTPUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUTPUT_DIR/spotter-$STAMP.sql.gz"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set; nothing to back up." >&2
  exit 1
fi

# Parse postgres connection details from DATABASE_URL.
# Expected form: postgres://user:pass@host:port/dbname
python3 - "$DATABASE_URL" "$FILE" <<'PY'
import gzip, os, subprocess, sys, urllib.parse
url = sys.argv[1]
out = sys.argv[2]
parsed = urllib.parse.urlparse(url)
env = dict(os.environ)
env["PGPASSWORD"] = parsed.password or ""
cmd = [
    "pg_dump",
    "-h", parsed.hostname or "localhost",
    "-p", str(parsed.port or 5432),
    "-U", parsed.username or "postgres",
    "-d", (parsed.path or "/spotter").lstrip("/"),
    "--no-owner",
    "--no-privileges",
]
with open(out, "wb") as fh:
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)
    with gzip.GzipFile(fileobj=fh, mode="wb") as gz:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            gz.write(chunk)
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"pg_dump failed with code {rc}")
print(f"Backup written to {out}")
PY

# Retention: keep the last 14 backups.
ls -1t "$OUTPUT_DIR"/spotter-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Retention applied (keeping 14 most recent)."

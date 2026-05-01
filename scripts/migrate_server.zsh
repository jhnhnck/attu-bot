#!/usr/bin/env zsh
# Migrates the postgres_data volume to a new server and starts all services.
# Run from the prod project directory (/srv/services/doom-bot).
# The target server must already have the repository cloned at TARGET_DIR.
# Source services are left stopped after migration.
#
# Usage: scripts/migrate_server.zsh [--ssh-user USER] [--target-dir DIR] [--dry-run] TARGET_HOST
#
# Arguments:
#   TARGET_HOST              remote hostname or IP (required)
#   --ssh-user USER          ssh login username (default: $USER)
#   --target-dir DIR         project path on target (default: /srv/services/doom-bot)
#   --dry-run                trace all commands with set -x but do not execute

set -euo pipefail

# ─── argument parsing ────────────────────────────────────────────────────────
SSH_USER=${USER}
TARGET_DIR="/srv/services/doom-bot"
DRY_RUN=0
TARGET_HOST=""

while (( $# )); do
  case "$1" in
    --ssh-user)   SSH_USER="$2";   shift 2 ;;
    --target-dir) TARGET_DIR="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=1;       shift   ;;
    --help|-h)
      print "Usage: $0 [--ssh-user USER] [--target-dir DIR] [--dry-run] TARGET_HOST"
      exit 0
      ;;
    -*)
      print "unknown option: $1" >&2
      exit 1
      ;;
    *)
      TARGET_HOST="$1"
      shift
      ;;
  esac
done

if [[ -z "${TARGET_HOST}" ]]; then
  print "Usage: $0 [--ssh-user USER] [--target-dir DIR] [--dry-run] TARGET_HOST" >&2
  exit 1
fi

(( DRY_RUN )) && set -x

SSH_TARGET="${SSH_USER}@${TARGET_HOST}"
COMPOSE=(docker compose -f docker-compose.prod.yml)

# ─── detect project name and volume ─────────────────────────────────────────
PROJECT_NAME=$(
  "${COMPOSE[@]}" config 2>/dev/null | python3 -c "
import sys
for line in sys.stdin:
    if line.startswith('name:'):
        print(line.split(':', 1)[1].strip())
        break
" 2>/dev/null
) || true
[[ -n "${PROJECT_NAME}" ]] || PROJECT_NAME=$(basename "$(pwd)")
[[ -n "${PROJECT_NAME}" ]] || { print "error: could not detect project name" >&2; exit 1; }

POSTGRES_VOLUME="${PROJECT_NAME}_postgres_data"

# ─── local temp dir ──────────────────────────────────────────────────────────
TMPDIR_LOCAL=$(mktemp -d /tmp/doom-migrate-XXXXXX)
REMOTE_TMPDIR="/tmp/doom-migrate-$$"
trap '[[ -d "${TMPDIR_LOCAL}" ]] && rm -rf "${TMPDIR_LOCAL}"' EXIT

# ─── run helper: skips execution in dry-run mode ─────────────────────────────
run() {
  if (( DRY_RUN )); then
    print "[dry-run] $*"
  else
    "$@"
  fi
}

# ─── summary + confirmation ──────────────────────────────────────────────────
print ""
print "  project : ${PROJECT_NAME}"
print "  volume  : ${POSTGRES_VOLUME}"
print "  target  : ${SSH_TARGET}:${TARGET_DIR}"
print ""

if (( ! DRY_RUN )); then
  print "this will stop all services on this server and transfer postgres_data to the target."
  print "source services will be LEFT STOPPED after migration."
  print -n "continue? [y/N] "
  read -r CONFIRM
  [[ "${CONFIRM}" =~ ^[Yy]$ ]] || { print "aborted."; exit 0; }
fi

# ─── [1/7] disk space check ──────────────────────────────────────────────────
print "\n==> [1/7] checking disk space..."
if (( ! DRY_RUN )); then
  POSTGRES_VOLUME="${POSTGRES_VOLUME}" python3 - << 'PYEOF'
import subprocess, shutil, sys, os

vol = os.environ["POSTGRES_VOLUME"]
r = subprocess.run(
    ["docker", "run", "--rm", "-v", f"{vol}:/data:ro", "alpine", "du", "-sb", "/data"],
    capture_output=True, text=True, check=True,
)
vol_bytes = int(r.stdout.split()[0])
free_bytes = shutil.disk_usage("/tmp").free
print(f"    volume: {vol_bytes // 1_048_576} MB  |  /tmp free: {free_bytes // 1_048_576} MB")
if free_bytes < vol_bytes * 1.5:
    need_mb = int(vol_bytes * 1.5) // 1_048_576
    print(f"error: not enough free space in /tmp — need ~{need_mb} MB", file=sys.stderr)
    sys.exit(1)
PYEOF
else
  print "[dry-run] check: volume size vs /tmp free space"
fi

# ─── [2/7] stop local services ───────────────────────────────────────────────
print "\n==> [2/7] stopping local services..."
run "${COMPOSE[@]}" stop core web ingestor   # dependents first
run "${COMPOSE[@]}" stop ferret              # middleware
run "${COMPOSE[@]}" stop postgres qdrant llama-server

# ─── [3/7] dump postgres_data ────────────────────────────────────────────────
print "\n==> [3/7] dumping ${POSTGRES_VOLUME}..."
run docker run --rm \
  -v "${POSTGRES_VOLUME}:/data:ro" \
  -v "${TMPDIR_LOCAL}:/backup" \
  alpine tar czf /backup/postgres_data.tar.gz -C /data .

# ─── [4/7] rsync to target ───────────────────────────────────────────────────
print "\n==> [4/7] transferring to ${SSH_TARGET}..."
run ssh "${SSH_TARGET}" "mkdir -p '${REMOTE_TMPDIR}'"
run rsync -az --info=progress2 "${TMPDIR_LOCAL}/" "${SSH_TARGET}:${REMOTE_TMPDIR}/"

# ─── [5/7] load volume on target ─────────────────────────────────────────────
print "\n==> [5/7] loading volume on target..."
if (( ! DRY_RUN )); then
  ssh "${SSH_TARGET}" bash << EOF
set -euo pipefail

[[ -d "${TARGET_DIR}" ]] || { echo "error: ${TARGET_DIR} not found on remote" >&2; exit 1; }
cd "${TARGET_DIR}"

docker volume create "${POSTGRES_VOLUME}" 2>/dev/null || true
docker run --rm \
  -v "${POSTGRES_VOLUME}:/data" \
  -v "${REMOTE_TMPDIR}:/backup:ro" \
  alpine sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null || true; tar xzf /backup/postgres_data.tar.gz -C /data'
echo "volume loaded"

# mark postgres_data external so compose uses the loaded volume rather than creating a fresh one
python3 - "${POSTGRES_VOLUME}" << 'PYEOF'
import sys, re

vol  = sys.argv[1]
path = "docker-compose.prod.yml"

with open(path) as f:
    text = f.read()

if "name: " + vol not in text:
    text = re.sub(
        r"^(  postgres_data:)\s*$",
        r"\1\n    external: true\n    name: " + vol,
        text,
        flags=re.MULTILINE,
    )
    with open(path, "w") as f:
        f.write(text)
    print("patched docker-compose.prod.yml -> postgres_data external: " + vol)
else:
    print("docker-compose.prod.yml already declares external volume")
PYEOF
EOF
else
  print "[dry-run] ssh ${SSH_TARGET}: create ${POSTGRES_VOLUME}, extract tarball, patch docker-compose.prod.yml"
fi

# ─── [6/7] build and start on target ─────────────────────────────────────────
print "\n==> [6/7] starting services on target..."
if (( ! DRY_RUN )); then
  ssh "${SSH_TARGET}" bash << EOF
set -euo pipefail
cd "${TARGET_DIR}"
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml ps
EOF
else
  print "[dry-run] ssh ${SSH_TARGET}: docker compose -f docker-compose.prod.yml up --build -d"
fi

# ─── [7/7] remote cleanup ────────────────────────────────────────────────────
print "\n==> [7/7] cleaning up remote temp dir..."
run ssh "${SSH_TARGET}" "rm -rf '${REMOTE_TMPDIR}'"

print ""
print "migration complete."
print "source services are stopped. to restart them here if needed:"
print "  ${COMPOSE[*]} up -d"

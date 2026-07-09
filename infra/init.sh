#!/usr/bin/env bash
#
# init.sh — provision the AWS infrastructure (SQS job queue + DLQ + IAM user)
# with Terraform and wire the resulting values into backend/.env.
#
# Follows the steps in instructions.md. Run from anywhere:
#   ./infra/init.sh            # provision + populate backend/.env
#   ./infra/init.sh destroy    # tear everything down
#
set -euo pipefail

# This script lives in infra/, so its own dir IS the Terraform dir.
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"
ENV_FILE="$REPO_DIR/backend/.env"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; }

# --- 1. Prerequisites ------------------------------------------------------
check_prereqs() {
  local missing=0
  for cmd in terraform aws session-manager-plugin; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      err "'$cmd' is not installed."
      case "$cmd" in
      terraform) echo "  Must install terraform" >&2 ;;
      aws) echo "  Must install aws-cli" >&2 ;;
      session-manager-plugin) echo " Must install aws session-manager-plugin" ;;
      esac
      missing=1
    fi
  done
  [ "$missing" -eq 0 ] || exit 1
}

# --- 2. Authenticate Terraform (admin credentials) -------------------------
# Bridge `aws login` cached credentials into env vars Terraform understands.
# Harmless if `aws configure` was used instead.
auth() {
  log "Bridging AWS credentials into environment variables for Terraform..."
  if creds="$(aws configure export-credentials --format env 2>/dev/null)"; then
    eval "$creds"
  fi

  log "Verifying AWS authentication..."
  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    err "Not authenticated to AWS. Run 'aws login' (or 'aws configure') first."
    exit 1
  fi
}

# --- 3. Provision the infrastructure ---------------------------------------
provision() {
  log "Initializing Terraform..."
  terraform -chdir="$INFRA_DIR" init -input=false

  log "Planning..."
  terraform -chdir="$INFRA_DIR" plan -input=false

  log "Applying (creates the queues + IAM user)..."
  terraform -chdir="$INFRA_DIR" apply
}

# --- 4. Populate backend/.env ----------------------------------------------
populate_env() {
  log "Writing infra outputs to $ENV_FILE ..."
  out() { terraform -chdir="$INFRA_DIR" output -raw "$1"; }

  {
    echo "SQS_QUEUE_URL=$(out queue_url)"
    echo "SQS_DLQ_URL=$(out dlq_url)"
    echo "AWS_REGION=$(out aws_region)"
    echo "AWS_ACCESS_KEY_ID=$(out app_access_key_id)"
    echo "AWS_SECRET_ACCESS_KEY=$(out app_secret_access_key)"
  } >>"$ENV_FILE"

  log "Done. Remember to add your Supabase values to $ENV_FILE:"
  echo "  DB_URL=..."
  echo "  DB_SERVICE_KEY=..."
}

# --- 5. Tear down ----------------------------------------------------------
destroy() {
  check_prereqs
  auth
  log "Destroying all Terraform-managed infrastructure..."
  terraform -chdir="$INFRA_DIR" destroy
}

main() {
  case "${1:-}" in
  destroy)
    destroy
    ;;
  "" | apply | up)
    check_prereqs
    auth
    provision
    populate_env
    log "Infrastructure is up. "
    ;;
  *)
    err "Unknown command: $1"
    echo "Usage: $0 [apply|destroy]" >&2
    exit 1
    ;;
  esac
}

main "$@"

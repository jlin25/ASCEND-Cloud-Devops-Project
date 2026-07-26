#!/usr/bin/env bash
#
# init.sh — provision the AWS infrastructure (S3 + SQS queue + DLQ + IAM + EC2
# worker) with Terraform, then interactively reconcile:
#   - terraform.tfvars: worker_repo_url / worker_branch, so the EC2 worker
#     actually runs worker.py instead of booting as a bare, unused box.
#   - backend/.env: every key the backend needs to launch.
# Both reconciles are per-key confirm/prompt, and write in place (re-runs
# never create duplicate lines / silently leave the worker undeployed).
#
# Run from anywhere:
#   ./infra/init.sh            # provision + reconcile backend/.env
#   ./infra/init.sh env        # reconcile backend/.env only (skip provisioning)
#   ./infra/init.sh destroy    # tear everything down
#
set -euo pipefail

# This script lives in infra/, so its own dir IS the Terraform dir.
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"
ENV_FILE="$REPO_DIR/backend/.env"
TFVARS_FILE="$INFRA_DIR/terraform.tfvars"

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
# Terraform's `resource` blocks always mean "create this" — there's no
# "create only if missing" in the language itself. So if a bucket with our
# name already exists in AWS but isn't in Terraform's state (e.g. left over
# from an interrupted apply, or created out-of-band), `apply` would try to
# create a duplicate and fail with BucketAlreadyOwnedByYou/AlreadyExists.
# adopt_orphans() closes that gap: for each resource we know the real-world
# name of, check AWS directly; if it exists but isn't tracked, `terraform
# import` it so apply reconciles it instead of re-creating it.
adopt_orphans() {
  local bucket
  bucket="$(grep -E '^\s*bucket\s*=' "$INFRA_DIR/s3.tf" | head -1 | sed -E 's/.*"(.*)".*/\1/')"

  if terraform -chdir="$INFRA_DIR" state list aws_s3_bucket.file_storage >/dev/null 2>&1; then
    return # already tracked; nothing to adopt
  fi

  if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    log "S3 bucket '$bucket' already exists in AWS but isn't in Terraform state — importing it instead of creating a duplicate."
    terraform -chdir="$INFRA_DIR" import aws_s3_bucket.file_storage "$bucket"
  fi
}

# --- 3b. Worker code deployment (terraform.tfvars) --------------------------
# Without worker_repo_url set, ec2.tf still provisions the box (Python 3.11,
# ffmpeg, IAM role, SSM config) but boots it BARE — no worker.py, no systemd
# service — because user_data.sh.tftpl only clones/runs the worker when a repo
# URL is present. This bit us silently before: infra looked "up" but nothing
# was actually consuming the job queue. Reconcile these two vars the same way
# as backend/.env so it's never a silent gap again.

get_tfvar() {
  grep -E "^\s*$1\s*=" "$TFVARS_FILE" 2>/dev/null | tail -n1 | sed -E 's/^[^=]*=\s*"?([^"]*)"?\s*$/\1/'
}

set_tfvar() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^\s*${key}\s*=" "$TFVARS_FILE" 2>/dev/null > "$tmp" || true
  printf '%s = "%s"\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$TFVARS_FILE"
}

# TF_VAR_<KEY> in the environment always wins over terraform.tfvars (that's
# Terraform's own precedence), so if it's set we just report it and move on —
# prompting to edit the file would be misleading since apply won't use it.
#   $1 key, $2 note shown once (context/requirements), $3 message shown when
#   missing (what happens if you skip), $4 default suggested when skipping.
reconcile_tfvar() {
  local key="$1" note="$2" missing_msg="$3" default_val="${4-}" env_name="TF_VAR_${key}" ans cur nv
  if [ -n "${!env_name:-}" ]; then
    log "$key: using \$$env_name from the environment (overrides terraform.tfvars)"
    return
  fi

  cur="$(get_tfvar "$key")"
  if [ -n "$cur" ]; then
    printf '  %s currently = %s\n' "$key" "$cur"
    prompt "    Keep it? [Y/n] " ans
    case "$ans" in
    n|N) prompt "    Enter new $key: " nv
         [ -n "$nv" ] && set_tfvar "$key" "$nv" || log "$key: left unchanged (blank entry)" ;;
    *) : ;; # keep as-is, no rewrite needed
    esac
    return
  fi

  [ -n "$note" ] && printf '  %s\n' "$note"
  printf '  %s is not set. %s\n' "$key" "$missing_msg"
  prompt "    Enter $key (blank to skip): " nv
  if [ -n "$nv" ]; then set_tfvar "$key" "$nv"; log "$key: set"
  elif [ -n "$default_val" ]; then set_tfvar "$key" "$default_val"; log "$key: using default '$default_val'"
  else log "$key: skipped"; fi
}

reconcile_worker_deploy() {
  touch "$TFVARS_FILE"
  reconcile_tfvar worker_repo_url \
    "Git URL of THIS repo. Must be public — user_data does a plain 'git clone', no deploy key/token support." \
    "Without it, the EC2 worker boots as a BARE box (Python/ffmpeg installed, but no worker.py, no systemd service) and never consumes the job queue."
  reconcile_tfvar worker_branch "" \
    "Branch to deploy on the worker. Only matters if worker_repo_url is set." \
    "main"
}

provision() {
  log "Initializing Terraform..."
  terraform -chdir="$INFRA_DIR" init -input=false

  adopt_orphans
  reconcile_worker_deploy

  log "Planning..."
  terraform -chdir="$INFRA_DIR" plan -input=false

  log "Applying (creates the queues + IAM user)..."
  terraform -chdir="$INFRA_DIR" apply
}

# --- 4. Populate backend/.env (idempotent, interactive) --------------------
# Each key is reconciled individually: if it already exists we show it and ask
# whether to keep or replace it; if it's missing (or you choose to change it) we
# prompt. Writing always REPLACES the key in place — never appends — so re-runs
# can't produce duplicate lines.

# Read the current value of KEY from .env ("" if absent). Last wins if dup'd.
get_env() {
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2-
}

# Write KEY=VALUE, removing every prior line for KEY first (collapses dups).
set_env() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^${key}=" "$ENV_FILE" 2>/dev/null > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
}

# Should this key's value be hidden when displayed?
is_secret_key() {
  case "$1" in
  *SECRET*|*ACCESS_KEY*|*SERVICE_KEY*) return 0 ;;
  *) return 1 ;;
  esac
}

# Mask a value for display: show a hint, not the whole secret.
mask() {
  local v="$1"
  if [ "${#v}" -le 8 ]; then echo "********"; else echo "${v:0:4}…${v: -2}"; fi
}

prompt() { read -rp "$1" "$2" </dev/tty 2>/dev/null || eval "$2=''"; }

display() { if is_secret_key "$1"; then mask "$2"; else printf '%s' "$2"; fi; }

# Reconcile one key.
#   KIND=tf     : NEW is the authoritative terraform output for this key.
#   KIND=manual : NEW is ignored; value comes from you (with a generator for
#                 SECRET_KEY if you leave it blank).
reconcile_key() {
  local key="$1" kind="$2" new="${3-}" cur ans
  cur="$(get_env "$key")"

  if [ -n "$cur" ]; then
    if [ "$kind" = "tf" ] && [ "$new" = "$cur" ]; then
      set_env "$key" "$cur"   # collapse any duplicates, no change
      log "$key: unchanged ($(display "$key" "$cur"))"
      return
    fi
    if [ "$kind" = "tf" ]; then
      printf '  %s\n    current : %s\n    new (tf): %s\n' \
        "$key" "$(display "$key" "$cur")" "$(display "$key" "$new")"
      prompt "    Replace with the new terraform value? [y/N] " ans
      case "$ans" in y|Y) set_env "$key" "$new"; log "$key: replaced" ;;
                     *)   set_env "$key" "$cur"; log "$key: kept" ;; esac
    else
      printf '  %s currently = %s\n' "$key" "$(display "$key" "$cur")"
      prompt "    Keep it? [Y/n] " ans
      case "$ans" in
      n|N) local nv; prompt "    Enter new $key: " nv
           set_env "$key" "$nv"; log "$key: updated" ;;
      *)   set_env "$key" "$cur"; log "$key: kept" ;;
      esac
    fi
    return
  fi

  # Not present yet.
  if [ "$kind" = "tf" ]; then
    set_env "$key" "$new"; log "$key: set from terraform"
  else
    printf '  %s is not set.\n' "$key"
    local nv; prompt "    Enter $key (blank to skip): " nv
    if [ -z "$nv" ] && [ "$key" = "SECRET_KEY" ]; then
      prompt "    Generate a random SECRET_KEY? [Y/n] " ans
      case "$ans" in n|N) : ;;
        *) nv="$(python3 -c 'import secrets;print(secrets.token_hex(32))' 2>/dev/null \
                 || openssl rand -hex 32)" ;; esac
    fi
    if [ -n "$nv" ]; then set_env "$key" "$nv"; log "$key: set"
    else log "$key: skipped (blank)"; fi
  fi
}

populate_env() {
  log "Reconciling $ENV_FILE (per-key confirm; existing values never duplicated)..."
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  out() { terraform -chdir="$INFRA_DIR" output -raw "$1"; }

  # From terraform outputs (authoritative).
  reconcile_key SQS_QUEUE_URL         tf "$(out queue_url)"
  reconcile_key SQS_DLQ_URL           tf "$(out dlq_url)"
  reconcile_key S3_BUCKET_NAME        tf "$(out bucket_name)"
  reconcile_key AWS_REGION            tf "$(out aws_region)"
  reconcile_key AWS_ACCESS_KEY_ID     tf "$(out app_access_key_id)"
  reconcile_key AWS_SECRET_ACCESS_KEY tf "$(out app_secret_access_key)"

  # Supplied by you (not in terraform). Prompted if missing.
  reconcile_key DB_URL          manual
  reconcile_key DB_SERVICE_KEY  manual
  reconcile_key SECRET_KEY      manual

  log "$ENV_FILE is ready."
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
    log "Infrastructure is up and backend/.env is ready."
    ;;
  env)
    # Reconcile backend/.env without (re)provisioning. Needs infra already
    # applied so terraform outputs exist.
    check_prereqs
    auth
    populate_env
    ;;
  *)
    err "Unknown command: $1"
    echo "Usage: $0 [apply|env|destroy]" >&2
    exit 1
    ;;
  esac
}

main "$@"

#!/usr/bin/env python3
"""
init.py — provision the AWS infrastructure (S3 + SQS queue + DLQ + IAM + EC2
worker) with Terraform, then interactively reconcile:

  - terraform.tfvars: worker_repo_url / worker_branch, so the EC2 worker
    actually runs worker.py instead of booting as a bare, unused box.
  - backend/.env: every key the backend needs to launch.

Both reconciles are per-key confirm/prompt, and always upsert in place —
re-runs never create duplicate lines or silently leave the worker undeployed.

This replaces an earlier bash version. Two bash pitfalls drove the rewrite:
`local a=$1 b=$a` in one statement doesn't see `a` (words are expanded before
`local` declares anything), and a `grep | tail | cut` pipeline that finds no
match trips `pipefail` even though the later stages succeed on empty input —
both failed silently under `set -e`. Doing the same logic in Python removes
the entire class of bug.

Usage (also runnable via ./infra/init.sh, which just execs this):
  ./infra/init.py            # provision + reconcile tfvars + .env
  ./infra/init.py env        # reconcile backend/.env only (skip provisioning)
  ./infra/init.py destroy    # tear everything down
  ./infra/init.py destroy --keep-bucket   # tear down all but the S3 bucket
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent
REPO_DIR = INFRA_DIR.parent
ENV_FILE = REPO_DIR / "backend" / ".env"
TFVARS_FILE = INFRA_DIR / "terraform.tfvars"


# --- output helpers ----------------------------------------------------------


def log(msg: str) -> None:
    print(f"\033[1;34m==>\033[0m {msg}")


def err(msg: str) -> None:
    print(f"\033[1;31mError:\033[0m {msg}", file=sys.stderr)


def prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return ""


# --- subprocess helpers -------------------------------------------------------


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command with output/stdin passed through live; exit on failure."""
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def run_ok(cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a command quietly; return whether it succeeded."""
    result = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stripped stdout, or "" if it fails."""
    result = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def terraform(*args: str) -> None:
    run(["terraform", *args], cwd=INFRA_DIR)


def terraform_ok(*args: str) -> bool:
    return run_ok(["terraform", *args], cwd=INFRA_DIR)


def terraform_output(name: str) -> str:
    return capture(["terraform", "output", "-raw", name], cwd=INFRA_DIR)


# --- 1. Prerequisites ---------------------------------------------------------


def check_prereqs() -> None:
    hints = {
        "terraform": "Must install terraform",
        "aws": "Must install aws-cli",
        "session-manager-plugin": "Must install aws session-manager-plugin",
    }
    missing = [cmd for cmd in hints if shutil.which(cmd) is None]
    for cmd in missing:
        err(f"'{cmd}' is not installed.")
        print(f"  {hints[cmd]}", file=sys.stderr)
    if missing:
        sys.exit(1)


# --- 2. Authenticate Terraform (admin credentials) ----------------------------
# Bridge `aws login` cached credentials into env vars Terraform understands.
# Harmless if `aws configure` was used instead (static keys just pass through).


def auth() -> None:
    log("Bridging AWS credentials into environment variables for Terraform...")
    creds = capture(
        ["aws", "configure", "export-credentials", "--format", "env-no-export"]
    )
    for line in creds.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

    log("Verifying AWS authentication...")
    if not run_ok(["aws", "sts", "get-caller-identity"]):
        err("Not authenticated to AWS. Run 'aws login' (or 'aws configure') first.")
        sys.exit(1)


# --- 3. Provision the infrastructure ------------------------------------------
# Terraform's `resource` blocks always mean "create this" — there's no
# "create only if missing" in the language itself. So if a bucket with our
# name already exists in AWS but isn't in Terraform's state (e.g. left over
# from an interrupted apply, or created out-of-band), `apply` would try to
# create a duplicate and fail with BucketAlreadyOwnedByYou/AlreadyExists.
# adopt_orphans() closes that gap: for each resource we know the real-world
# name of, check AWS directly; if it exists but isn't tracked, `terraform
# import` it so apply reconciles it instead of re-creating it.


def tf_console_eval(expr: str) -> str:
    """Evaluate a Terraform expression (e.g. "var.project_name") via `terraform
    console`. Only needs `terraform init` to have run — no apply/state
    required for plain variable lookups."""
    result = subprocess.run(
        ["terraform", "console"],
        cwd=INFRA_DIR,
        input=expr,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip().strip('"') if result.returncode == 0 else ""


def adopt_resource_if_orphan(
    address: str, exists_cmd: list[str], import_id: str, label: str
) -> None:
    """If `address` isn't in Terraform state but the real AWS resource exists,
    import it instead of letting `apply` fail on a duplicate-create error."""
    if terraform_ok("state", "list", address):
        return  # already tracked

    if run_ok(exists_cmd):
        log(
            f"{label} already exists in AWS but isn't in Terraform state — "
            "importing it instead of creating a duplicate."
        )
        terraform("import", address, import_id)


def adopt_orphans() -> None:
    # IAM/S3 resources are the common source of partial-apply leftovers: if
    # `apply` fails partway through (e.g. on the SSM/EC2 step), anything it
    # already created stays in AWS but never makes it into state, so the next
    # run's `apply` dies on EntityAlreadyExists/BucketAlreadyOwnedByYou.
    project_name = tf_console_eval("var.project_name")
    if not project_name:
        return
    account_id = capture(
        ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]
    )
    if not account_id:
        return  # can't build the bucket name / policy ARNs without it

    # Region-scoped resources (S3, EC2) must be checked in the SAME region
    # Terraform is configured for — otherwise a bucket/SG can appear to exist
    # (via the CLI's default region) while being invisible to the region the
    # provider actually imports into, which fails with "non-existent remote
    # object". IAM is a global service, so it's unaffected by this.
    region = tf_console_eval("var.aws_region") or capture(
        ["aws", "configure", "get", "region"]
    )
    region_args = ["--region", region] if region else []

    # Bucket name is interpolated in s3.tf (project name + account id) — build
    # the resolved name directly rather than regexing the raw HCL, which only
    # yields the unresolved "${var.project_name}-file-storage-${...}" string.
    bucket = f"{project_name}-file-storage-{account_id}"
    adopt_resource_if_orphan(
        "aws_s3_bucket.file_storage",
        ["aws", "s3api", "head-bucket", "--bucket", bucket, *region_args],
        bucket,
        f"S3 bucket '{bucket}'",
    )

    user_name = f"{project_name}-backend"
    adopt_resource_if_orphan(
        "aws_iam_user.app",
        ["aws", "iam", "get-user", "--user-name", user_name],
        user_name,
        f"IAM user '{user_name}'",
    )

    worker_name = f"{project_name}-worker"
    adopt_resource_if_orphan(
        "aws_iam_role.worker",
        ["aws", "iam", "get-role", "--role-name", worker_name],
        worker_name,
        f"IAM role '{worker_name}'",
    )
    adopt_resource_if_orphan(
        "aws_iam_instance_profile.worker",
        ["aws", "iam", "get-instance-profile", "--instance-profile-name", worker_name],
        worker_name,
        f"IAM instance profile '{worker_name}'",
    )
    # Security groups are imported by group-id, not name, so look that up first.
    sg_id = capture(
        [
            "aws",
            "ec2",
            "describe-security-groups",
            "--filters",
            f"Name=group-name,Values={worker_name}",
            "--query",
            "SecurityGroups[0].GroupId",
            "--output",
            "text",
            *region_args,
        ]
    )
    if sg_id and sg_id != "None":
        adopt_resource_if_orphan(
            "aws_security_group.worker",
            ["aws", "ec2", "describe-security-groups", "--group-ids", sg_id, *region_args],
            sg_id,
            f"Security group '{worker_name}' ({sg_id})",
        )

    for address, policy_name in (
        ("aws_iam_policy.jobs_access", f"{project_name}-jobs-access"),
        ("aws_iam_policy.ssm_read", f"{project_name}-ssm-read"),
    ):
        policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
        adopt_resource_if_orphan(
            address,
            ["aws", "iam", "get-policy", "--policy-arn", policy_arn],
            policy_arn,
            f"IAM policy '{policy_name}'",
        )


# --- 3b. Worker code deployment (terraform.tfvars) ----------------------------
# Without worker_repo_url set, ec2.tf still provisions the box (Python 3.11,
# ffmpeg, IAM role, SSM config) but boots it BARE — no worker.py, no systemd
# service — because user_data.sh.tftpl only clones/runs the worker when a repo
# URL is present. This bit us silently before: infra looked "up" but nothing
# was actually consuming the job queue. Reconcile these two vars the same way
# as backend/.env so it's never a silent gap again.


def get_tfvar(key: str) -> str | None:
    if not TFVARS_FILE.exists():
        return None
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*"?([^"]*)"?\s*$')
    value = None
    for line in TFVARS_FILE.read_text().splitlines():
        m = pattern.match(line)
        if m:
            value = m.group(1)
    return value


def set_tfvar(key: str, value: str) -> None:
    lines = TFVARS_FILE.read_text().splitlines() if TFVARS_FILE.exists() else []
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    lines = [ln for ln in lines if not pattern.match(ln)]
    lines.append(f'{key} = "{value}"')
    TFVARS_FILE.write_text("\n".join(lines) + "\n")


def reconcile_tfvar(
    key: str, note: str = "", missing_msg: str = "", default_val: str = ""
) -> None:
    # TF_VAR_<KEY> in the environment always wins over terraform.tfvars (that's
    # Terraform's own precedence), so if it's set we just report it and move
    # on — prompting to edit the file would be misleading since apply won't
    # use it.
    env_name = f"TF_VAR_{key}"
    if os.environ.get(env_name):
        log(
            f"{key}: using ${env_name} from the environment (overrides terraform.tfvars)"
        )
        return

    cur = get_tfvar(key)
    if cur:
        print(f"  {key} currently = {cur}")
        if prompt("    Keep it? [Y/n] ").lower() == "n":
            nv = prompt(f"    Enter new {key}: ")
            if nv:
                set_tfvar(key, nv)
            else:
                log(f"{key}: left unchanged (blank entry)")
        return

    if note:
        print(f"  {note}")
    print(f"  {key} is not set. {missing_msg}")
    nv = prompt(f"    Enter {key} (blank to skip): ")
    if nv:
        set_tfvar(key, nv)
        log(f"{key}: set")
    elif default_val:
        set_tfvar(key, default_val)
        log(f"{key}: using default '{default_val}'")
    else:
        log(f"{key}: skipped")


def reconcile_worker_deploy() -> None:
    TFVARS_FILE.touch(exist_ok=True)
    reconcile_tfvar(
        "worker_repo_url",
        note="Git URL of THIS repo. Must be public — user_data does a plain "
        "'git clone', no deploy key/token support.",
        missing_msg="Without it, the EC2 worker boots as a BARE box "
        "(Python/ffmpeg installed, but no worker.py, no systemd "
        "service) and never consumes the job queue.",
    )
    reconcile_tfvar(
        "worker_branch",
        missing_msg="Branch to deploy on the worker. Only matters if "
        "worker_repo_url is set.",
        default_val="main",
    )


def export_supabase_tfvars() -> None:
    """db_url/db_service_key (iam.tf's SSM parameters) have no usable default
    — apply fails with a validation error if they're blank. They're marked
    `sensitive` in variables.tf, so unlike worker_repo_url/branch we export
    them as TF_VAR_* env vars instead of writing them into terraform.tfvars
    (which would put secrets in a plaintext file)."""
    for tf_key, env_key in (("db_url", "DB_URL"), ("db_service_key", "DB_SERVICE_KEY")):
        tf_var = f"TF_VAR_{tf_key}"
        if os.environ.get(tf_var):
            continue  # already provided by the caller's shell

        value = get_env(env_key)  # reuse whatever's already in backend/.env
        if not value:
            print(
                f"  {env_key} is required (stored as a SecureString in SSM for the worker)."
            )
            value = prompt(f"    Enter {env_key}: ")
        if not value:
            err(
                f"{env_key} must be set — Terraform will fail creating the SSM parameter without it."
            )
            sys.exit(1)
        os.environ[tf_var] = value


def infra_up_to_date() -> bool:
    """True if `terraform plan` reports no changes (exit code 0 with
    -detailed-exitcode means no diff; 2 means changes are pending)."""
    result = subprocess.run(
        ["terraform", "plan", "-input=false", "-detailed-exitcode"],
        cwd=INFRA_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def provision() -> None:
    log("Initializing Terraform...")
    terraform("init", "-input=false")

    adopt_orphans()
    reconcile_worker_deploy()
    export_supabase_tfvars()

    log("Planning...")
    if infra_up_to_date():
        log("Infrastructure is already up to date — skipping apply.")
        return

    terraform("plan", "-input=false")

    log("Applying (creates the queues + IAM user)...")
    terraform("apply")


# --- 4. Populate backend/.env (idempotent, interactive) -----------------------
# Each key is reconciled individually: if it already exists we show it and ask
# whether to keep or replace it; if it's missing (or you choose to change it)
# we prompt. Writing always REPLACES the key in place — never appends — so
# re-runs can't produce duplicate lines.


def get_env(key: str) -> str | None:
    if not ENV_FILE.exists():
        return None
    prefix = f"{key}="
    value = None
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :]
    return value


def set_env(key: str, value: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    prefix = f"{key}="
    lines = [ln for ln in lines if not ln.startswith(prefix)]
    lines.append(f"{key}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(lines) + "\n")


def is_secret_key(key: str) -> bool:
    return any(marker in key for marker in ("SECRET", "ACCESS_KEY", "SERVICE_KEY"))


def mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * 8
    return f"{value[:4]}…{value[-2:]}"


def display(key: str, value: str) -> str:
    return mask(value) if is_secret_key(key) else value


def reconcile_env_key(key: str, kind: str, new: str = "") -> None:
    """kind: 'tf' (new is the authoritative terraform output) or 'manual'
    (value comes from you, with a generator offered for SECRET_KEY)."""
    cur = get_env(key)

    if cur:
        if kind == "tf":
            if new == cur:
                set_env(key, cur)  # collapse any duplicate lines, no change
                log(f"{key}: unchanged ({display(key, cur)})")
                return
            print(f"  {key}")
            print(f"    current : {display(key, cur)}")
            print(f"    new (tf): {display(key, new)}")
            if (
                prompt("    Replace with the new terraform value? [y/N] ").lower()
                == "y"
            ):
                set_env(key, new)
                log(f"{key}: replaced")
            else:
                set_env(key, cur)
                log(f"{key}: kept")
        else:
            print(f"  {key} currently = {display(key, cur)}")
            if prompt("    Keep it? [Y/n] ").lower() == "n":
                nv = prompt(f"    Enter new {key}: ")
                set_env(key, nv)
                log(f"{key}: updated")
            else:
                set_env(key, cur)
                log(f"{key}: kept")
        return

    # Not present yet.
    if kind == "tf":
        set_env(key, new)
        log(f"{key}: set from terraform")
    else:
        print(f"  {key} is not set.")
        nv = prompt(f"    Enter {key} (blank to skip): ")
        if not nv and key == "SECRET_KEY":
            if prompt("    Generate a random SECRET_KEY? [Y/n] ").lower() != "n":
                nv = secrets.token_hex(32)
        if nv:
            set_env(key, nv)
            log(f"{key}: set")
        else:
            log(f"{key}: skipped (blank)")


def populate_env() -> None:
    log(
        f"Reconciling {ENV_FILE} (per-key confirm; existing values never duplicated)..."
    )
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.touch(exist_ok=True)

    # From terraform outputs (authoritative).
    reconcile_env_key("SQS_QUEUE_URL", "tf", terraform_output("queue_url"))
    reconcile_env_key("SQS_DLQ_URL", "tf", terraform_output("dlq_url"))
    reconcile_env_key("S3_BUCKET_NAME", "tf", terraform_output("bucket_name"))
    reconcile_env_key("AWS_REGION", "tf", terraform_output("aws_region"))
    reconcile_env_key("AWS_ACCESS_KEY_ID", "tf", terraform_output("app_access_key_id"))
    reconcile_env_key(
        "AWS_SECRET_ACCESS_KEY", "tf", terraform_output("app_secret_access_key")
    )

    # Supplied by you (not in terraform). Prompted if missing.
    reconcile_env_key("DB_URL", "manual")
    reconcile_env_key("DB_SERVICE_KEY", "manual")
    reconcile_env_key("SECRET_KEY", "manual")

    verify_supabase_credentials()

    log(f"{ENV_FILE} is ready.")


# --- 4b. Verify Supabase credentials -------------------------------------------
# DB_URL/DB_SERVICE_KEY are supplied by hand (not from terraform), so a typo or
# stale key wouldn't surface until the backend/worker try to talk to Supabase
# at runtime. Hit the REST root with the key to confirm it's present and
# actually accepted before declaring infra "ready".


def verify_supabase_credentials() -> None:
    url = get_env("DB_URL")
    key = get_env("DB_SERVICE_KEY")

    if not url or not key:
        err(
            "Supabase credentials incomplete: DB_URL and/or DB_SERVICE_KEY are not set in backend/.env."
        )
        sys.exit(1)

    endpoint = f"{url.rstrip('/')}/rest/v1/"
    req = urllib.request.Request(
        endpoint, headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        log("Supabase credentials verified (DB_URL/DB_SERVICE_KEY accepted).")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            err(
                f"Supabase rejected DB_SERVICE_KEY ({e.code} {e.reason}) — check the key in backend/.env."
            )
            sys.exit(1)
        # Any other HTTP status (e.g. 404 on the REST root) still means the
        # request reached Supabase with an accepted key.
        log("Supabase credentials verified (DB_URL/DB_SERVICE_KEY accepted).")
    except urllib.error.URLError as e:
        err(f"Could not reach Supabase at {url}: {e.reason}")
        sys.exit(1)


# --- 5. Tear down --------------------------------------------------------------


def clear_untracked_access_keys() -> None:
    """IAM won't delete a user that still has access keys, but `aws_iam_access_key`
    can end up untracked (e.g. `destroy` partially completing, or a key rotated
    by hand) while `aws_iam_user.app` is still in state — the last `terraform
    destroy` died exactly this way: DeleteConflict on ascend-backend because a
    key it didn't know about was still attached. Delete any keys Terraform
    isn't tracking before destroy runs, so the user delete can't get stuck."""
    if not terraform_ok("state", "list", "aws_iam_user.app"):
        return  # user isn't tracked (or infra never provisioned) — nothing to do

    project_name = tf_console_eval("var.project_name")
    if not project_name:
        return
    user_name = f"{project_name}-backend"

    tracked_key_id = capture(
        ["terraform", "state", "show", "-no-color", "aws_iam_access_key.app"], cwd=INFRA_DIR
    )
    tracked_key_id = next(
        (
            line.split("=", 1)[1].strip().strip('"')
            for line in tracked_key_id.splitlines()
            if line.strip().startswith("id ")
        ),
        None,
    )

    import json

    keys_json = capture(
        ["aws", "iam", "list-access-keys", "--user-name", user_name, "--output", "json"]
    )
    if not keys_json:
        return
    for meta in json.loads(keys_json).get("AccessKeyMetadata", []):
        key_id = meta["AccessKeyId"]
        if key_id == tracked_key_id:
            continue  # Terraform will delete this one itself as part of destroy
        log(f"Deleting untracked access key {key_id} on IAM user '{user_name}' so destroy isn't blocked...")
        run_ok(["aws", "iam", "delete-access-key", "--user-name", user_name, "--access-key-id", key_id])


# Everything in s3.tf. Dropping these from state (rather than destroying them)
# leaves the bucket and its files in AWS; the next `./infra/init.sh` re-imports
# the bucket via adopt_orphans() and re-applies the settings resources.
BUCKET_ADDRESSES = (
    "aws_s3_bucket.file_storage",
    "aws_s3_bucket_versioning.file_storage_versioning",
    "aws_s3_bucket_server_side_encryption_configuration.file_storage_encryption",
    "aws_s3_bucket_public_access_block.file_storage_public_block",
)


def destroy(keep_bucket: bool = False) -> None:
    check_prereqs()
    auth()
    terraform("init", "-input=false")
    clear_untracked_access_keys()
    if keep_bucket:
        for address in BUCKET_ADDRESSES:
            if terraform_ok("state", "list", address):
                log(f"Keeping {address}: removing it from state so destroy skips it...")
                terraform("state", "rm", address)
        log("Destroying all Terraform-managed infrastructure except the S3 bucket...")
    else:
        log("Destroying all Terraform-managed infrastructure...")
    terraform("destroy")


# --- main ------------------------------------------------------------------


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "destroy":
        flags = argv[2:]
        if flags not in ([], ["--keep-bucket"]):
            err(f"Unknown destroy option(s): {' '.join(flags)}")
            sys.exit(1)
        destroy(keep_bucket=flags == ["--keep-bucket"])
    elif cmd in ("", "apply", "up"):
        check_prereqs()
        auth()
        provision()
        populate_env()
        log("Infrastructure is up and backend/.env is ready.")
    elif cmd == "env":
        # Reconcile backend/.env without (re)provisioning. Needs infra
        # already applied so terraform outputs exist.
        check_prereqs()
        auth()
        populate_env()
    else:
        err(f"Unknown command: {cmd}")
        print(f"Usage: {argv[0]} [apply|env|destroy [--keep-bucket]]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)

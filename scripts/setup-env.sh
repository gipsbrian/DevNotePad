#!/usr/bin/env bash
# Interactively writes the repo-root .env file. Values are entered at a
# prompt (not passed as command/make arguments), and the token is read with
# echo disabled -- so nothing sensitive ends up in shell history or in
# `ps`/`history` output the way `make setup GIT_TOKEN=...` would.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  read -r -p ".env already exists at $ENV_FILE. Overwrite? [y/N] " confirm
  case "$confirm" in
    [yY]*) ;;
    *) echo "Leaving existing .env untouched."; exit 0 ;;
  esac
fi

echo "Setting up DevNotePad's .env"
echo "Scope the token to the repos you use, with Issues: Read-only (or Read & write to close issues and comment)."
echo "(Both values are optional -- you can also set a token per dashboard in the app instead.)"
echo

read -r -p "Default GitHub org/user URL, e.g. https://github.com/my-org [optional]: " GIT_ORG_URL

echo -n "Default GitHub token (input hidden; leave blank to skip): "
read -r -s GIT_TOKEN
echo

# Encrypts stored GitHub tokens. Generated rather than prompted for —
# it's machine-generated key material, not something to type in.
SECRET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || true)"
if [ -z "$SECRET_KEY" ]; then
  echo "Could not generate SECRET_KEY: python3 needs the 'cryptography' package." >&2
  echo "Run 'make install' first, then re-run 'make setup'." >&2
  exit 1
fi

# The account that signs in to the app. Created on first startup, and
# only ever into an empty user table -- changing these later won't
# rewrite an existing account's password.
echo
echo "Now the account you'll sign in with."
read -r -p "Username: " ADMIN_USERNAME
read -r -p "Email: " ADMIN_EMAIL
echo -n "Password (input hidden): "
read -r -s ADMIN_PASSWORD
echo

if [ -z "$ADMIN_USERNAME" ] || [ -z "$ADMIN_EMAIL" ] || [ -z "$ADMIN_PASSWORD" ]; then
  echo "All three are required -- without them nobody can sign in." >&2
  exit 1
fi

{
  echo "GIT_TOKEN=${GIT_TOKEN}"
  echo "GIT_ORG_URL=${GIT_ORG_URL}"
  echo "SECRET_KEY=${SECRET_KEY}"
  echo "ADMIN_USERNAME=${ADMIN_USERNAME}"
  echo "ADMIN_EMAIL=${ADMIN_EMAIL}"
  echo "ADMIN_PASSWORD=${ADMIN_PASSWORD}"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo
echo "Wrote $ENV_FILE (permissions set to 600, and it's gitignored)."
echo "Reminder: scope this token to specific repos with Issues: Read-only"
echo "(or Read & write only if you want to close issues / post comments from"
echo "the app). Avoid granting full 'repo' or organization-wide access."

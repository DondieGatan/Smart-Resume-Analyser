#!/usr/bin/env bash
# Publish the current commit to a Hugging Face Space (Docker SDK).
#
#   HF_SPACE=<hf-username>/<space-name> bash deploy/huggingface/deploy.sh
#
# Git asks for your Hugging Face username and, as the password, an access token with write
# access (huggingface.co/settings/tokens). Nothing secret is stored in or sent from this repo:
# the app's settings (DATABASE_URL, SECRET_KEY, ...) are added once in the Space's
# Settings > Variables and secrets. Only tracked files are published, so .env and uploads/
# never leave your machine.
set -euo pipefail

: "${HF_SPACE:?Set HF_SPACE to <hf-username>/<space-name>}"

ROOT="$(git rev-parse --show-toplevel)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git -C "$ROOT" archive HEAD | tar -x -C "$TMP"
rm -rf "$TMP/screenshots" "$TMP/tests" "$TMP/.github" "$TMP/.claude" "$TMP/deploy"
cp "$ROOT/deploy/huggingface/Dockerfile" "$TMP/Dockerfile"
cp "$ROOT/deploy/huggingface/README.md" "$TMP/README.md"

cd "$TMP"
git init -q -b main
git add -A
git commit -q -m "Deploy $(git -C "$ROOT" rev-parse --short HEAD)"
git push --force "https://huggingface.co/spaces/${HF_SPACE}" main
echo "Pushed. Build progress: https://huggingface.co/spaces/${HF_SPACE}"

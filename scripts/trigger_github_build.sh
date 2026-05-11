#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/trigger_github_build.sh <version> [branch]

Examples:
  scripts/trigger_github_build.sh 1.0.17
  scripts/trigger_github_build.sh v1.0.17 main

Requirements:
  - GitHub CLI (`gh`) installed
  - `gh auth login` completed
  - Run from inside the repository or keep this script in the repository
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

version="${1:-}"
branch="${2:-}"

if [[ -z "$version" ]]; then
  usage
  exit 1
fi

normalized_version="${version#v}"
if [[ ! "$normalized_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "Invalid version: $version" >&2
  echo "Expected format: 1.0.17 or v1.0.17" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI not found. Please install gh first: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Please run: gh auth login" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [[ -z "$branch" ]]; then
  branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
fi

echo "Triggering GitHub Actions build"
echo "Version: v$normalized_version"
echo "Branch:  $branch"

(
  cd "$repo_root"
  gh workflow run "Build and Release" \
    --ref "$branch" \
    --field "version=v$normalized_version"
)

echo "Build triggered. View runs with: gh run list --workflow \"Build and Release\""

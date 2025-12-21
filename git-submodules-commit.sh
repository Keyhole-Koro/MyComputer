#!/usr/bin/env bash
set -euo pipefail

msg=""
exclude=""
include=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m) msg="${2:-}"; shift 2 ;;
    -ex) exclude="${2:-}"; shift 2 ;;
    -my) include="${2:-}"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$msg" ]]; then
  echo "Usage: $0 -m \"commit message\" [-ex \"sub1 sub2\"] [-my \"sub1 sub2\"]" >&2
  exit 1
fi

# Always operate from the repo that contains this script (superproject)
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$script_dir"

if [[ ! -f "$repo_root/.gitmodules" ]]; then
  echo "No .gitmodules in $repo_root; are you running in the superproject?" >&2
  exit 1
fi

mapfile -t subs < <(git -C "$repo_root" config --file .gitmodules --get-regexp path | awk '{print $2}')

if [[ ${#subs[@]} -eq 0 ]]; then
  echo "No submodules found." >&2
  exit 0
fi

should_include() {
  local name="$1"
  if [[ -n "$include" ]]; then
    for i in $include; do
      [[ "$name" == "$i" ]] && return 0
    done
    return 1
  fi
  if [[ -n "$exclude" ]]; then
    for e in $exclude; do
      [[ "$name" == "$e" ]] && return 1
    done
  fi
  return 0
}

for sub in "${subs[@]}"; do
  name="${sub##*/}"
  if ! should_include "$name"; then
    continue
  fi

  if [[ -n "$(git -C "$repo_root/$sub" status --porcelain)" ]]; then
    echo "==> $sub"
    git -C "$repo_root/$sub" add -A
    git -C "$repo_root/$sub" commit -m "$msg"
    git -C "$repo_root/$sub" push origin HEAD
  else
    echo "==> $sub (no changes)"
  fi
done

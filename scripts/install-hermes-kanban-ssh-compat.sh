#!/usr/bin/env bash
set -euo pipefail

SSH_TARGET="${SSH_TARGET:-nik1t7n@wanderer}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/hermes_desktop_wanderer}"
REMOTE_HERMES_DIR="${REMOTE_HERMES_DIR:-\$HOME/.hermes/hermes-agent}"

ssh_args=()
if [[ -n "${SSH_KEY}" ]]; then
  ssh_args+=("-i" "${SSH_KEY}")
fi
ssh_args+=("-o" "BatchMode=yes" "${SSH_TARGET}")

ssh "${ssh_args[@]}" "REMOTE_HERMES_DIR='${REMOTE_HERMES_DIR}' bash -s" <<'REMOTE'
set -euo pipefail

eval "hermes_dir=${REMOTE_HERMES_DIR}"
venv_dir="${hermes_dir}/venv"
bin="${venv_dir}/bin/hermes"
python_bin="${venv_dir}/bin/python3"

if [[ ! -x "${python_bin}" ]]; then
  echo "missing venv python: ${python_bin}" >&2
  exit 1
fi

if [[ ! -e "${bin}" ]]; then
  echo "missing Hermes entrypoint: ${bin}" >&2
  exit 1
fi

if ! grep -q "Hermes Desktop SSH compatibility entrypoint" "${bin}" 2>/dev/null; then
  backup="${bin}.backup-before-desktop-kanban-wrapper-$(date +%Y%m%d-%H%M%S)"
  cp "${bin}" "${backup}"
  echo "backup: ${backup}"
else
  echo "wrapper already installed; refreshing in place"
fi

tmp="$(mktemp)"
cat > "${tmp}" <<PY
#!${python_bin}
# -*- coding: utf-8 -*-
"""Hermes Desktop SSH compatibility entrypoint.

Hermes Desktop 0.4.5 can split Kanban values with spaces when it builds SSH
commands. Rebuild only the affected Kanban argv fields before delegating to the
real Hermes CLI module.
"""

import sys

from hermes_cli.main import main


VALUE_OPTIONS = {
    "--body",
    "--name",
    "--reason",
    "--result",
    "--tenant",
    "--workspace",
}


def merge_option_values(argv):
    out = []
    i = 0
    while i < len(argv):
        current = argv[i]
        out.append(current)
        if current in VALUE_OPTIONS and i + 1 < len(argv):
            j = i + 1
            value = []
            while j < len(argv) and not argv[j].startswith("--"):
                value.append(argv[j])
                j += 1
            if value:
                out.append(" ".join(value))
            i = j
            continue
        i += 1
    return out


def split_at_options(items):
    positional = []
    i = 0
    while i < len(items) and not items[i].startswith("--"):
        positional.append(items[i])
        i += 1
    return positional, items[i:]


def normalize_kanban_tail(tail):
    if not tail:
        return tail

    if tail[0] == "boards":
        if len(tail) >= 3 and tail[1] == "create":
            return tail[:3] + merge_option_values(tail[3:])
        return tail

    cmd = tail[0]

    if cmd == "create":
        positional, rest = split_at_options(tail[1:])
        if positional:
            return [cmd, " ".join(positional)] + merge_option_values(rest)
        return [cmd] + merge_option_values(rest)

    if cmd == "comment" and len(tail) >= 3:
        return [cmd, tail[1], " ".join(tail[2:])]

    if cmd in {"complete", "reclaim"}:
        return tail[:2] + merge_option_values(tail[2:])

    return tail


def normalize_argv(argv):
    try:
        kanban_index = argv.index("kanban")
    except ValueError:
        return argv
    return argv[: kanban_index + 1] + normalize_kanban_tail(argv[kanban_index + 1 :])


if __name__ == "__main__":
    sys.argv[1:] = normalize_argv(sys.argv[1:])
    if sys.argv[0].endswith("-script.pyw"):
        sys.argv[0] = sys.argv[0][:-11]
    elif sys.argv[0].endswith(".exe"):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
PY

install -m 755 "${tmp}" "${bin}"
rm -f "${tmp}"

if [[ ! -e "${hermes_dir}/.venv" ]]; then
  ln -s "${venv_dir}" "${hermes_dir}/.venv"
  echo "created symlink: ${hermes_dir}/.venv -> ${venv_dir}"
fi

"${bin}" --version | head -n 5
REMOTE

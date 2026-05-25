# Hermes Desktop Kanban Remote Setup Runbook

Last verified: 2026-05-23

This document captures the working setup for using Hermes Desktop on macOS with a remote Hermes server over SSH tunnel mode, including the Kanban fix for `ssh command failed`.

## What Was Fixed

Hermes Desktop `0.4.5` generated remote SSH commands like:

```sh
bash -c '... hermes 'kanban' 'create' 'title with spaces' ...'
```

That looks safe, but it is not. The outer single quotes make Bash strip or break the inner quoted arguments. As a result:

- task titles with spaces were split into multiple argv items
- bodies/comments/reasons with spaces could be parsed incorrectly
- apostrophes or newlines could break the shell before `hermes` even started
- the UI surfaced the failure as the generic message `ssh command failed`

The working setup has two layers:

1. A patched Hermes Desktop command builder that wraps the whole remote script safely with `bash -lc <quoted-script>`.
2. A server-side compatibility wrapper around the remote `venv/bin/hermes` entrypoint, so older Desktop builds are less fragile when they split Kanban arguments with spaces.

## Current Working Machine State

Mac app:

```text
/Applications/Hermes Agent.app
/Users/nik1t7n/Applications/Hermes Agent.app
```

Backup of the original app:

```text
/Applications/Hermes Agent.original-v0.4.5-20260523-123140.app
```

Remote server:

```text
SSH target: nik1t7n@wanderer
Remote Hermes repo: /home/nik1t7n/.hermes/hermes-agent
Remote Hermes venv: /home/nik1t7n/.hermes/hermes-agent/venv
Remote Hermes entrypoint: /home/nik1t7n/.hermes/hermes-agent/venv/bin/hermes
Remote port: 8642
Desktop local tunnel port: 18642
```

Desktop config path:

```text
/Users/nik1t7n/.hermes/desktop.json
```

Working config shape, with secrets intentionally redacted:

```json
{
  "locale": "en",
  "connectionMode": "ssh",
  "remoteUrl": "https://agents.nik1t7n.work",
  "remoteApiKey": "<redacted>",
  "sshConfig": {
    "host": "wanderer",
    "port": 22,
    "username": "nik1t7n",
    "keyPath": "/Users/nik1t7n/.ssh/hermes_desktop_wanderer",
    "remotePort": 8642,
    "localPort": 18642
  }
}
```

## Files To Preserve

For a smooth setup on another Mac, preserve or recreate these:

- The patched app build, or the source patch described below.
- `/Users/nik1t7n/.hermes/desktop.json`, with secrets handled through a private channel.
- `/Users/nik1t7n/.ssh/hermes_desktop_wanderer`, or create a fresh SSH key and add its public key to the server.
- The server-side wrapper installed at `/home/nik1t7n/.hermes/hermes-agent/venv/bin/hermes`.
- The smoke test script at `scripts/hermes-desktop-kanban-smoke.js`.
- The wrapper installer at `scripts/install-hermes-kanban-ssh-compat.sh`.

Do not store API keys, Cloudflare tokens, or private SSH keys in git.

## Fresh Mac Setup

1. Install Hermes Desktop.

Use the patched build if available. If starting from upstream `fathah/hermes-desktop`, rebuild it with the patch in the next section.

2. Configure SSH.

Create a key if this Mac does not already have one:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/hermes_desktop_wanderer -C hermes-desktop-wanderer
```

Add the public key to the server:

```sh
ssh-copy-id -i ~/.ssh/hermes_desktop_wanderer.pub nik1t7n@wanderer
```

Verify passwordless SSH:

```sh
ssh -i ~/.ssh/hermes_desktop_wanderer -o BatchMode=yes nik1t7n@wanderer 'echo ok'
```

3. Restore Desktop config.

Create or edit:

```text
~/.hermes/desktop.json
```

Use SSH mode, not plain remote mode, because Kanban currently depends on SSH/local behavior.

4. Install the server-side compatibility wrapper.

From this repo:

```sh
SSH_TARGET=nik1t7n@wanderer \
SSH_KEY="$HOME/.ssh/hermes_desktop_wanderer" \
REMOTE_HERMES_DIR="$HOME/.hermes/hermes-agent" \
scripts/install-hermes-kanban-ssh-compat.sh
```

5. Open Hermes Desktop and verify the tunnel.

```sh
open "/Applications/Hermes Agent.app"
curl -sf http://127.0.0.1:18642/health
```

Expected:

```json
{"status":"ok","platform":"hermes-agent"}
```

6. Run the Kanban smoke test.

```sh
SSH_TARGET=nik1t7n@wanderer \
SSH_KEY="$HOME/.ssh/hermes_desktop_wanderer" \
KANBAN_RESTORE_BOARD=cognee-external \
node scripts/hermes-desktop-kanban-smoke.js
```

Expected final line:

```text
OK
```

## Desktop Source Patch

Source file:

```text
src/main/ssh-remote.ts
```

Patch the `buildRemoteHermesCmd` function so the entire generated remote script is quoted as one shell argument:

```ts
function buildRemoteHermesCmd(args: string[], extraShell = ""): string {
  const candidates = [
    "$HOME/hermes-agent/.venv/bin/hermes",
    "$HOME/.hermes/hermes-agent/.venv/bin/hermes",
    "/opt/hermes/hermes-agent/.venv/bin/hermes",
  ];
  const quotedArgs = args.map((a) => shellQuote(a)).join(" ");
  const probe = candidates
    .map((p) => `[ -x ${p} ] && exec ${p} ${quotedArgs}${extraShell}`)
    .join("; ");
  const script = `${probe}; command -v hermes >/dev/null && exec hermes ${quotedArgs}${extraShell}; echo "ERR: hermes CLI not found on remote PATH or in any known venv location" >&2; exit 1`;
  return `bash -lc ${shellQuote(script)}`;
}
```

Build on Apple Silicon:

```sh
npm ci
npm run typecheck:node
npm run test -- tests/ssh-remote.test.ts
npm run build:unpack
```

Install the unpacked app:

```sh
rm -rf "$HOME/Applications/Hermes Agent.app"
mkdir -p "$HOME/Applications"
ditto "dist/mac-arm64/Hermes Agent.app" "$HOME/Applications/Hermes Agent.app"
xattr -dr com.apple.quarantine "$HOME/Applications/Hermes Agent.app" 2>/dev/null || true
codesign --verify --deep --strict --verbose=1 "$HOME/Applications/Hermes Agent.app"
open "$HOME/Applications/Hermes Agent.app"
```

If replacing `/Applications/Hermes Agent.app`, keep the original app as a backup first.

## Server-Side Wrapper

The wrapper is intentionally conservative:

- It imports and runs `hermes_cli.main` like the original generated entrypoint.
- It only rewrites argv for `hermes kanban ...`.
- It merges known single-value fields that Desktop may split: title, body, board name, tenant, workspace, reclaim reason, completion result.
- It does not change non-Kanban commands.

Install it with:

```sh
scripts/install-hermes-kanban-ssh-compat.sh
```

The installer backs up the original entrypoint before replacing it.

## Kanban Verification Checklist

Run these after any new install, Desktop update, Hermes update, or server migration:

- Desktop shows `Connected to remote Hermes`.
- Kanban opens in SSH tunnel mode.
- `curl http://127.0.0.1:18642/health` returns healthy JSON.
- `node scripts/hermes-desktop-kanban-smoke.js` ends with `OK`.
- Remote DB integrity is clean:

```sh
ssh -i ~/.ssh/hermes_desktop_wanderer nik1t7n@wanderer 'python3 - <<PY
import sqlite3
from pathlib import Path
for p in [Path.home()/".hermes/kanban.db", Path.home()/".hermes/kanban/boards/cognee-external/kanban.db"]:
    con = sqlite3.connect(p)
    print(p, con.execute("pragma integrity_check").fetchone()[0])
    con.close()
PY'
```

## Troubleshooting

If the UI says `Plain remote mode does not yet expose the kanban API`, switch Desktop Settings to SSH tunnel mode.

If the UI says `ssh command failed`, run:

```sh
ssh -i ~/.ssh/hermes_desktop_wanderer -o BatchMode=yes nik1t7n@wanderer 'echo ok'
node scripts/hermes-desktop-kanban-smoke.js
```

If smoke fails on apostrophes or newlines, the Desktop app is probably not patched.

If smoke fails only on titles/bodies with spaces, the server-side wrapper is probably missing or was overwritten by a Hermes reinstall/update.

If a Hermes update overwrites `venv/bin/hermes`, reinstall the wrapper:

```sh
scripts/install-hermes-kanban-ssh-compat.sh
```

## Hand-Off Summary

When moving to another Mac, transfer:

- patched Hermes Desktop build or instructions to rebuild it
- `desktop.json` with secrets provided separately
- SSH key setup instructions or a new generated SSH key
- this runbook
- `scripts/install-hermes-kanban-ssh-compat.sh`
- `scripts/hermes-desktop-kanban-smoke.js`

The quality gate is simple: after setup, the smoke test must end with `OK`, and the Desktop Kanban UI must allow creating a task with a normal sentence title and body without `ssh command failed`.

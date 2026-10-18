# OpenCode ⇄ Antigravity MCP Integration

**Status:** verified working end-to-end on 2026-10-18
**Owner:** `l41n-pr0t0` · **Host:** `wirednavi0x17` (NixOS 26.05, x86_64)

---

## 1. Architecture and communication flow

```
┌───────────────────────────┐
│  Antigravity CLI (`agy`)  │  MCP client
└─────────────┬─────────────┘
              │  MCP over stdio
              │  (newline-delimited JSON-RPC 2.0,
              │   spawned as a child process)
              ▼
┌───────────────────────────────────────────────┐
│  opencode-bridge  (localhost, stateless)      │
│  ~/.local/share/opencode-bridge/              │
│      opencode_bridge.py                       │
│  Python 3 stdlib only, zero third-party deps  │
└─────────────┬─────────────────────────────────┘
              │  HTTP + HTTP Basic auth
              │  127.0.0.1:4096 (loopback only)
              ▼
┌───────────────────────────────────────────────┐
│  opencode serve --hostname 127.0.0.1          │
│      --port 4096                              │
│  systemd user service:                        │
│      opencode-antigravity.service             │
└─────────────┬─────────────────────────────────┘
              │
              ▼
   OpenCode V2 engine (sessions, agents, providers, tools)
```

**Why a custom bridge instead of an off-the-shelf package**

This was established by inspection, not assumption:

| Candidate | Result |
|---|---|
| OpenCode V2 native MCP server | **Does not exist.** `/api/mcp*` routes manage MCP *clients* OpenCode consumes. `opencode serve --stdio` prints `{"url": ...}` and serves HTTP — it is not an MCP transport. |
| `opencode acp` | Real JSON-RPC server, but the **Agent Client Protocol**, not MCP. Antigravity does not speak ACP. |
| `opencode-mcp@3.0.0` (npm, latest) | **Incompatible.** Imports the legacy `@opencode-ai/sdk` root entrypoint (V1 paths `/session`, `/config`) while the installed server is V2.0.32. Measured failure: `opencode_health` → *"Status: unhealthy"*, `opencode_session_list` → *"sessions.map is not a function"* (the V1 routes return the web-UI SPA HTML, not JSON). |
| **Custom bridge (chosen)** | Targets V2's documented `/api/*` surface; zero dependencies; fully auditable. |

The bridge is **stateless**. All session state lives in the OpenCode server, which is why
sessions survive bridge process restarts (each `agy` invocation spawns a fresh bridge process).

---

## 2. Software versions and prerequisites

| Component | Version | Notes |
|---|---|---|
| NixOS | 26.05 (Yarara), kernel 6.18.46 | x86_64 |
| opencode | **2.0.32** | `~/.local/bin/opencode` → self-contained ELF, no Node needed |
| Antigravity | package 1.23.2 / **CLI 1.1.21** | `agy`, from `/run/current-system/sw/bin` |
| Python | 3.13.15 | `/run/current-system/sw/bin/python3` |
| systemd (user) | running | `XDG_RUNTIME_DIR=/run/user/1001` |
| Node.js / npm | 24.19.0 / 11.17.0 | **not required** by this integration |

**Prerequisites:** a running `opencode-antigravity.service`, and the
`~/.config/opencode-bridge/credentials.env` file (mode 0600) present.

---

## 3. Configuration locations (no secrets)

| Purpose | Path | Mode |
|---|---|---|
| MCP bridge source | `~/.local/share/opencode-bridge/opencode_bridge.py` | 0755 |
| systemd unit | `~/.config/systemd/user/opencode-antigravity.service` | 0644 |
| Antigravity MCP config | `~/.gemini/config/mcp_config.json` | 0644 |
| **Credentials (contains secret)** | `~/.config/opencode-bridge/credentials.env` | **0600** |
| Backup of previous MCP config | `~/.gemini/config/mcp_config.json.bak-20261018-183436` | 0644 |
| This document | `~/.local/share/opencode-bridge/INTEGRATION.md` | 0644 |

### Antigravity MCP entry (`~/.gemini/config/mcp_config.json`)

Antigravity's documented schema supports **stdio** (`command`/`args`/`env`) and **SSE**
(`serverUrl`). This integration uses stdio. The secret is **not** in this file — only the
path to the 0600 credentials file:

```json
{
  "mcpServers": {
    "opencode": {
      "command": "/run/current-system/sw/bin/python3",
      "args": ["/home/l41n-pr0t0/.local/share/opencode-bridge/opencode_bridge.py"],
      "env": {
        "OPENCODE_BASE_URL": "http://127.0.0.1:4096",
        "OPENCODE_BRIDGE_ENV_FILE": "/home/l41n-pr0t0/.config/opencode-bridge/credentials.env"
      }
    }
  }
}
```

Managed with the documented CLI too:

```bash
agy mcp list                                    # show configured servers
agy mcp add --env K=V opencode /path/to/cmd     # equivalent to the above
```

**Startup/shutdown/restart**

```bash
systemctl --user start   opencode-antigravity.service
systemctl --user stop    opencode-antigravity.service
systemctl --user restart opencode-antigravity.service
systemctl --user status  opencode-antigravity.service
```

Enabled at login via `default.target`. Note `Linger=no`: the service stops when the last
session for this user ends. Enable persistent operation with
`sudo loginctl enable-linger l41n-pr0t0` if it must run while logged out.

---

## 4. Health check and troubleshooting

```bash
# 1. is the service up and listening on loopback?
systemctl --user is-active opencode-antigravity.service
ss -tlnp | grep 4096

# 2. does the OpenCode API answer?  (password is read from the 0600 file, never echoed)
set -a; . ~/.config/opencode-bridge/credentials.env; set +a
curl -s -u "$OPENCODE_SERVER_USERNAME:$OPENCODE_SERVER_PASSWORD" \
     http://127.0.0.1:4096/api/info

# 3. does Antigravity see the server?
agy mcp list

# 4. end-to-end through the bridge
python3 ~/.local/share/opencode-bridge/opencode_bridge.py   # Ctrl-C to exit; logs to stderr only

# 5. service logs
journalctl --user -u opencode-antigravity.service -n 50 --no-pager
```

| Symptom | Cause | Fix |
|---|---|---|
| `[unreachable] ... Connection refused` | service not running | `systemctl --user start opencode-antigravity.service` |
| `[unauthorized] ... (HTTP 401)` | credentials mismatch | password in `credentials.env` must match the server's `OPENCODE_SERVER_PASSWORD`; restart the service after editing |
| `agy mcp list` shows no `opencode` | config not read | verify JSON in `~/.gemini/config/mcp_config.json`; restart the `agy` session |
| Unit `failed` after `stop` | cosmetic (OpenCode exits 130) | already handled by `SuccessExitStatus=130` |
| Tools listed but calls hang | backend busy on a long task | `oc_status`, then `oc_wait` — a timeout is **not** a failure |

---

## 5. Verified MCP tools

Discovered by Antigravity (confirmed: all 10 visible to the agent).

| Tool | Purpose | Verified |
|---|---|---|
| `oc_health` | server reachability, version, credential state | ✅ live |
| `oc_delegate` | create/continue a session, send a prompt, wait, return answer + changed files | ✅ live |
| `oc_session_create` | create a session bound to an absolute directory | ✅ |
| `oc_prompt` | fire a prompt asynchronously without waiting | ✅ live |
| `oc_wait` | block until idle, return final answer | ✅ live |
| `oc_status` | running/idle, message count, pending permissions | ✅ live |
| `oc_messages` | ordered session transcript | ✅ |
| `oc_diff` | changed files + patches (**latest turn only**, see §7) | ✅ live |
| `oc_sessions` | list recent sessions | ✅ live |
| `oc_abort` | interrupt a running session | ✅ |

**State and concurrency model (measured, not assumed)**

- **Session identifiers:** `ses_*`. Durable — stored by OpenCode, not the bridge.
- **Persistence:** a single session (`ses_eb0e15307ffeOcaGHZo5XZzMnE`) was driven across
  **four separate bridge processes** and retained full context each time.
- **Asynchronous:** `oc_prompt` returns immediately with a `msg_*` id. An `oc_status` call
  issued straight afterwards reported `state: running`.
- **Polling, not push:** the bridge emits **no** MCP progress notifications. Clients poll via
  `oc_wait` / `oc_status`. A wait timeout means *still running*, never *failed*.
- **Permissions:** if OpenCode needs approval, the session stalls and `oc_status` /
  `oc_wait` report `permissions: N pending`. The bridge never auto-approves.

---

## 6. Verification results

All tests were run through the real Antigravity CLI (`agy --print`), with results then
checked independently against the filesystem and `git`.

| # | Test | Result | Evidence |
|---|---|---|---|
| A | Server health | **PASS** | `/api/info` → version 2.0.32, loopback bound |
| B | MCP discovery | **PASS** | Antigravity enumerated all 10 `oc_*` tools |
| C | Basic invocation | **PASS** | `oc_health` returned live server data (pid 530191) |
| D | Execution test | **PASS** | `oc_delegate` created `stats.py` + `test_stats.py`, 6 unit tests |
| E | Independent verification | **PASS** | Re-ran suite: 6/6 OK. Found 2 uncovered `ValueError` branches |
| F | Revision test | **PASS** (3 rounds) | Round 1 → tests added (8/8). Round 2 → stale `__pycache__` claim **caught**. Round 3 → fixed; verified `__pycache__` absent, 8/8 tests pass |
| G | Failure handling | **PASS** | Service stopped → `[unreachable] Connection refused` surfaced in Antigravity; agent correctly reported "unavailable"; no false success. Restarted → immediate recovery |
| H | State and context | **PASS** | Async fire/poll confirmed; session survived 4 bridge restarts |

**Test F is the important one.** OpenCode reported *"removed `__pycache__`"* while the
directory still existed. Independent verification caught this; the true cause was that the
**mandated test re-run regenerated the bytecode**, so the fix required
`PYTHONDONTWRITEBYTECODE=1` (or cleanup *after* the run). This is a concrete demonstration
of why a delegated task must never be accepted on the agent's own word.

---

## 7. Safe collaboration protocol

1. **Antigravity defines** the task, acceptance criteria and constraints explicitly.
2. **Antigravity delegates** a bounded task via `oc_delegate` with an **absolute**
   `directory`, and a `timeoutSec` suited to the work.
3. **OpenCode inspects and implements** in that directory.
4. **OpenCode returns** a summary, changed-file list and stated test results.
5. **Antigravity reviews independently** — this step is mandatory:
   - `git status` / `git diff` in the shared directory (authoritative)
   - re-run the test suite itself
   - `oc_diff` and `oc_messages` for the agent's view
6. **Antigravity requests corrections** by calling `oc_delegate` again with the
   **same `sessionId`** and a precise, checkable criterion.
7. **OpenCode implements** the corrections.
8. **Antigravity verifies** again before accepting.

**Rules**

- Both agents must use the **same absolute working directory** for a task.
- **Never accept a completion claim without independent evidence** (test run + diff).
- Inspect **Git diffs** before accepting; run `git status` before and after.
- Never discard user work without explicit permission.
- Avoid overlapping writes: one session per directory at a time.
- Prefer `git worktree` or separate directories for parallel tasks — sessions do **not**
  isolate filesystem changes from each other.
- `oc_diff` shows **the latest turn only**. Use `git diff` against a known baseline for
  whole-task acceptance.

---

## 8. Known limitations and security

**Limitations**

- `oc_diff` is per-turn, not whole-session.
- No push notifications from the bridge — clients poll.
- `Linger=no`: the service stops when the user's last session ends unless lingering is enabled.
- The bridge is single-threaded; it handles one JSON-RPC frame at a time. A long
  `oc_delegate` blocks that bridge process until it returns (other bridge instances are
  unaffected).
- Options are not exposed for `session.revert`, `session.delete`, `share` or `instance
  dispose` — deliberately, to limit blast radius.

**Security considerations**

- The server binds **loopback only** (`127.0.0.1:4096`) and requires HTTP Basic auth.
  Do **not** rebind to `0.0.0.0`.
- The dedicated service has **its own credential pair**, independent of the user's shared
  OpenCode background service (which stays on its own ephemeral port). Stopping, restarting
  or rotating the bridge's credentials cannot disturb interactive TUI sessions.
- Secrets live only in `~/.config/opencode-bridge/credentials.env` (mode 0600) and are
  never printed, logged, or written into the Antigravity config.
- The bridge grants Antigravity the ability to run OpenCode work — which includes shell
  execution. Treat `agy` as having the same blast radius as OpenCode itself. Prefer
  `--mode plan` or restrictive OpenCode permissions for sensitive directories.
- OpenCode's own permission system still applies; the bridge never auto-approves.

**Recovery**

```bash
# credentials lost or rotated
printf 'OPENCODE_SERVER_USERNAME=opencode\nOPENCODE_SERVER_PASSWORD=%s\n' \
  "$(python3 -c 'import secrets,string;print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(48)))')" \
  > ~/.config/opencode-bridge/credentials.env
chmod 600 ~/.config/opencode-bridge/credentials.env
systemctl --user restart opencode-antigravity.service

# revert the Antigravity config entirely
cp ~/.gemini/config/mcp_config.json.bak-20261018-183436 ~/.gemini/config/mcp_config.json

# remove the integration
systemctl --user disable --now opencode-antigravity.service
rm ~/.config/systemd/user/opencode-antigravity.service
rm -rf ~/.local/share/opencode-bridge ~/.config/opencode-bridge
```

---

## 9. Unchanged by this work

- `~/.config/opencode/opencode.jsonc` — untouched (its `blender` MCP entry is preserved).
- The user's shared OpenCode background service (`opencode serve --service`) — untouched,
  still healthy on its own port.
- `/etc/nixos` and the Nix store — no changes; no `nixos-rebuild` was run.
- All pre-existing sessions, configuration and files — preserved.

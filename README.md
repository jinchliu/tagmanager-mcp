# tagmanager-mcp

An MCP (Model Context Protocol) server for the **Google Tag Manager API v2**.
Ask your AI assistant about your GTM setup — accounts, containers, tags,
triggers, variables, unpublished changes — and let it edit the workspace
draft: create, update and delete tags, triggers and variables. Works from
Claude Code, Claude Desktop, or any MCP client. Python, stdio transport,
built on the official `mcp` SDK.

## Why this one?

- **Authenticate once — no re-auth treadmill.** Auth is plain Google
  Application Default Credentials (ADC) with your own OAuth client: the
  refresh token does not expire, so you log in once and forget it. No hosted
  OAuth session that lapses every few days and demands another round of
  browser clicking.
- **No service account required.** The server runs as *you*, using the GTM
  permissions your Google account already has. There is no service-account
  JSON key to create, grant container access to, rotate, or accidentally
  commit.
- **Local and direct.** Runs on your machine over stdio; your GTM data flows
  straight between you and `tagmanager.googleapis.com`. No third-party proxy
  in the middle.
- **Built for LLM context windows.** GTM's raw tag JSON is enormous (a single
  GA4 event tag is easily hundreds of lines). `list_*` tools return slim
  skeletons; `get_*` tools fetch full detail only when asked.
- **Quota-aware by design.** The GTM API allows only 25 requests per 100
  seconds per project. The server retries rate limits (429/403) and server
  errors with exponential backoff, and self-throttles after the first hit.
  Errors come back as actionable messages, not raw stack traces.

## Tools

**Read (v0.1)**

| Tool | Purpose |
|---|---|
| `list_accounts` | GTM accounts you can access (optionally Google Tag accounts) |
| `list_containers` | Containers in an account |
| `list_workspaces` | Workspaces in a container |
| `get_workspace_status` | Unpublished changes and merge conflicts |
| `list_tags` / `get_tag` | Tags — skeleton list / full configuration |
| `list_triggers` / `get_trigger` | Triggers — skeleton list / full configuration |
| `list_variables` / `get_variable` | Variables — skeleton list / full configuration |

**Write (v0.2)**

| Tool | Purpose |
|---|---|
| `create_tag` / `create_trigger` / `create_variable` | Create an entity in the workspace draft |
| `update_tag` / `update_trigger` / `update_variable` | Merge partial changes into an entity |
| `delete_tag` / `delete_trigger` / `delete_variable` | Delete an entity (requires `confirm=true`) |

**Publish (v0.3)**

| Tool | Purpose |
|---|---|
| `list_versions` | Container version headers — skeleton list |
| `get_version` / `get_live_version` | One version / the currently live version, with slimmed contents |
| `create_version` | Snapshot the workspace into a version (consumes the workspace; returns `newWorkspacePath`) |
| `publish_version` | Publish a version live (requires `confirm=true`) |

The write safety model:

- **Editing and going live are separate.** Create/update/delete only touch
  the workspace draft; only `publish_version` changes what runs on the live
  site, and it needs `confirm=true`. You review changes in the GTM UI (or via
  `get_workspace_status` / `get_live_version`) before anything ships.
- **Updates are merge patches.** The model sends only the fields to change;
  the server re-reads the entity and submits its `fingerprint`, so a
  concurrent edit fails cleanly instead of being clobbered.
- **Deletes and publishing need explicit confirmation** (`confirm=true`) and
  are declared with `destructiveHint`. `create_version` is also destructive
  (it consumes the workspace) but does not gate on `confirm`.
- **No blind retries on writes.** Rate-limit rejections are retried (they
  happen before execution); ambiguous 5xx errors are not, so a create can
  never be silently duplicated.

## Prerequisites

- Python >= 3.10
- The [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- A Google account with access to your GTM containers
- Any GCP project you can enable an API on (used only for quota attribution)

## Setup

**1. Install**

```bash
git clone https://github.com/jinchliu/tagmanager-mcp && cd tagmanager-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

**2. Enable the Tag Manager API** on your quota project:

```bash
gcloud services enable tagmanager.googleapis.com --project=YOUR_PROJECT
```

**3. Create a Desktop OAuth client** (one-time, ~2 minutes).

Google blocks gcloud's built-in OAuth client for Tag Manager scopes
("This app is blocked"), so you bring your own:

- GCP Console → **Google Auth Platform → Clients → Create client** →
  Application type **Desktop app** → create, then download the JSON.
- On the **Audience** page, publish the app to **Production**. An app left
  in Testing status issues refresh tokens that expire after 7 days — the
  exact re-auth treadmill this project exists to avoid.

**4. Log in**

```bash
gcloud auth application-default login \
  --client-id-file=path/to/your-client.json \
  --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/cloud-platform
gcloud auth application-default set-quota-project YOUR_PROJECT
```

Scopes are additive to what each tier needs: drop `tagmanager.publish` +
`tagmanager.edit.containerversions` for edit-only (no publishing), or also
drop `tagmanager.edit.containers` for a read-only setup. Tools outside your
granted scopes fail with a clear re-login hint while everything else keeps
working.

The browser will warn "Google hasn't verified this app" — it is your own
app; choose Advanced → Continue.

> **Already using ADC for other Google tools** (BigQuery, analytics-mcp,
> ...)? Logging in replaces the ADC file, so include those scopes too, e.g.
> `--scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform`

**Verify** (expect HTTP 200 and your accounts):

```bash
curl -sS -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  https://tagmanager.googleapis.com/tagmanager/v2/accounts
```

## Connect an MCP client

**Claude Code**

```bash
claude mcp add gtm -- /absolute/path/to/tagmanager-mcp/.venv/bin/tagmanager-mcp
```

**Claude Desktop** (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "gtm": {
      "command": "/absolute/path/to/tagmanager-mcp/.venv/bin/tagmanager-mcp"
    }
  }
}
```

## Example prompts

- "Which GTM accounts and containers do I have?"
- "How many tags are in the default workspace of container GTM-XXXXXXX, grouped by type?"
- "Which tags are paused?"
- "Show me the full config of the purchase tag and which triggers fire it."
- "Does the current workspace have unpublished changes? What changed?"
- "Find triggers that no tag references."
- "Pause every tag that fires on the checkout trigger."
- "Create a custom-event trigger for `sign_up` and a GA4 event tag that
  fires on it."

## Quota

The GTM API is tightly limited: **10,000 requests/day** and **0.25 QPS
(25 requests per 100-second window) per GCP project** — per-user quota
overrides do not raise it. Ordinary audit conversations fit comfortably;
avoid "every tag in every container" sweeps across many containers at once.

## Troubleshooting

- **"This app is blocked" during login** — you used gcloud's default OAuth
  client; pass your own with `--client-id-file` (Setup step 3).
- **403 mentioning insufficient scopes** — your ADC predates this setup;
  re-run the login command in Setup step 4.
- **Errors mention enabling the API / quota project** — run Setup step 2 and
  `set-quota-project`; the error message itself carries the exact commands.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/nox -s tests    # stdlib unittest, fully offline
.venv/bin/nox -s lint     # black --check
.venv/bin/mcp dev tagmanager_mcp/server.py   # MCP Inspector
```

## Roadmap

- **v0.1**: read-only audit — `tagmanager.readonly`
- **v0.2**: create/update/delete for tags, triggers and variables in the
  workspace draft — adds `tagmanager.edit.containers`
- **v0.3** (current): version creation and publishing, kept architecturally
  separate from workspace editing — adds `tagmanager.edit.containerversions`
  and `tagmanager.publish`

# Google Tag Manager MCP Server (Alpha)

🚀 Empower your AI agents to handle the whole Google Tag Manager workflow!

This repo contains the source code for running a local 
[MCP](https://modelcontextprotocol.io/) server that interacts with APIs for 
[Google Tag Manager](https://support.google.com/tagmanager).

## Features

- **No frequent authentication.** Standard Google ADC with your own OAuth
  client is all you need. 
  Everything runs on your machine, straight against the GTM API.
- **No service account required.** The server runs as *you*, with the GTM
  permissions your account already has.
- **Built for LLM context windows.** A single GTM tag can be hundreds of
  lines of JSON; `list_*` tools return slim skeletons and `get_*` fetches
  full detail only when asked.

## Tools

The server uses the 
[Google Tag Manager API](https://developers.google.com/tag-platform/tag-manager/api/v2) 
to provide Tools for use with LLMs. 
The most frequently used tools are:

| Tool | Purpose |
|---|---|
| `list_containers` | Containers in an account — where every session starts |
| `list_tags` | Tags in the workspace as slim skeletons |
| `get_tag` | One tag's full configuration, on demand |
| `get_workspace_status` | Unpublished changes and merge conflicts |
| `create_tag` | Add a tag to the workspace draft |
| `update_tag` | Merge partial changes into a tag (fingerprint-checked) |
| `delete_tag` | Remove a tag (requires `confirm=true`) |

Triggers and variables have the same four tools as tags, and versioning and
publishing have their own. See
[Appendix I](#appendix-i-a-full-list-of-tools) for the full list.

The write safety model:

- **Editing and going live are separate.** Create/update/delete only touch
  the workspace draft; only `publish_version` changes the live site.
- **Updates are merge patches.** The model sends just the fields it changes,
  and the server submits the entity's `fingerprint`, so a concurrent edit
  fails cleanly instead of being clobbered.
- **Deletes and publishing need `confirm=true`**, and every destructive tool
  is declared with `destructiveHint`.
- **No blind retries on writes.** Rate-limit rejections are retried,
  ambiguous 5xx errors are not, so a create is never silently duplicated.

## Prerequisites

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/)
- The [gcloud CLI](https://docs.cloud.google.com/sdk/gcloud)
- A Google account with access to your GTM containers
- A GCP project (used only for quota attribution)

## Setup instructions

**1. Install**

```bash
pipx install tagmanager-mcp
```

**2. Enable the Tag Manager API** on your quota project

```bash
gcloud services enable tagmanager.googleapis.com --project=YOUR_PROJECT
```

**3. Create a Desktop OAuth client**

Check out
[Manage OAuth Clients](https://support.google.com/cloud/answer/15549257)
for how to create an OAuth client. Two choices matter here: pick
application type **Desktop app**, and publish the app to **Production**,
because an app left in Testing issues refresh tokens that expire after
7 days. Download the client JSON at the end — step 4 needs it.

Why your own client? Google may block gcloud's built-in one for Tag Manager
scopes ("This app is blocked"), and that block is not something you can
work around from your side.

**4. Log in**

```bash
gcloud auth application-default login \
  --client-id-file=path/to/your-client.json \
  --scopes=\
https://www.googleapis.com/auth/tagmanager.readonly,\
https://www.googleapis.com/auth/tagmanager.edit.containers,\
https://www.googleapis.com/auth/tagmanager.edit.containerversions,\
https://www.googleapis.com/auth/tagmanager.publish,\
https://www.googleapis.com/auth/cloud-platform

gcloud auth application-default set-quota-project YOUR_PROJECT
```

The browser will warn "Google hasn't verified this app" — it is your own
app; choose Advanced → Continue.

Those scopes unlock everything. Drop the lines you do not want:

| Scope | Unlocks |
|---|---|
| `tagmanager.readonly` | Every read tool |
| `tagmanager.edit.containers` | Create / update / delete in a workspace |
| `tagmanager.edit.containerversions` | `create_version` |
| `tagmanager.publish` | `publish_version` |
| `cloud-platform` | Nothing in GTM — needed by `set-quota-project` |

Tools outside your granted scopes fail with a clear re-login hint, and
everything else keeps working.

## Connect an MCP client

### Configure Claude Code

```bash
claude mcp add --scope user tagmanager-mcp -- tagmanager-mcp
```

`--scope user` registers the server for every project instead of just the
current directory. Verify with `claude mcp list`, or run `/mcp` inside a
session.

### Configure Claude Desktop

Claude Desktop needs the absolute path to the executable. Print it:

```bash
which tagmanager-mcp
```

Open **Settings → Developer → Edit Config**, which reveals
`claude_desktop_config.json`
(`~/Library/Application Support/Claude/` on macOS,
`%APPDATA%\Claude\` on Windows), and add the server with the path you just
printed:

```json
{
  "mcpServers": {
    "tagmanager-mcp": {
      "command": "/Users/you/.local/bin/tagmanager-mcp"
    }
  }
}
```

Save the file and restart Claude Desktop — it reads the config only at
startup. The tools then appear under the tools icon in the chat box.

## Example prompts

- "Which GTM accounts and containers do I have?"
- "How many tags are in container GTM-XXXXXXX, grouped by type?"
- "Show me the purchase tag's config and which triggers fire it."
- "Does the current workspace have unpublished changes?"
- "Pause every tag that fires on the checkout trigger."
- "Create a custom-event trigger for `sign_up` and a GA4 event tag that
  fires on it."

## Note on quota

The GTM API allows **10,000 requests/day** and **25 requests per 100
seconds** per GCP project; per-user overrides do not raise it. Ordinary
audit conversations fit comfortably — just avoid sweeping every tag across
many containers at once.

## Appendix I: A Full List of Tools

**Read**

| Tool | Purpose |
|---|---|
| `list_accounts` | GTM accounts you can access (optionally Google Tag accounts) |
| `list_containers` | Containers in an account |
| `list_workspaces` | Workspaces in a container |
| `get_workspace_status` | Unpublished changes and merge conflicts |
| `list_tags` / `get_tag` | Tags — skeleton list / full configuration |
| `list_triggers` / `get_trigger` | Triggers — skeleton list / full configuration |
| `list_variables` / `get_variable` | Variables — skeleton list / full configuration |
| `list_versions` | Container version headers — skeleton list |
| `get_version` / `get_live_version` | One version / the currently live version, with slimmed contents |

**Write**

| Tool | Purpose |
|---|---|
| `create_tag` / `create_trigger` / `create_variable` | Create an entity in the workspace draft |
| `update_tag` / `update_trigger` / `update_variable` | Merge partial changes into an entity |
| `delete_tag` / `delete_trigger` / `delete_variable` | Delete an entity (requires `confirm=true`) |
| `create_version` | Snapshot the workspace into a version (consumes the workspace; returns `newWorkspacePath`) |
| `publish_version` | Publish a version live (requires `confirm=true`) |

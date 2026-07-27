# tagmanager-mcp

Google Tag Manager MCP server in Python (stdio, FastMCP from the official
`mcp` SDK). v0.1 (read), v0.2 (write) and v0.3 (versions and publishing) are
shipped and verified against a real container — the v0.3 end-to-end smoke test
ran 2026-07-09. 24 tools (13 read + 11 write), 71 offline tests. Published on
PyPI as `tagmanager-mcp`; pushing a `v*` tag releases via GitHub Actions
Trusted Publishing (see "Releasing").

## Commands

```bash
.venv/bin/pip install -e ".[dev]"            # deps (venv + pip, no uv here)
.venv/bin/nox -s tests                       # stdlib unittest, tests/*_test.py
.venv/bin/nox -s lint                        # black --check
.venv/bin/nox -s format                      # black
.venv/bin/mcp dev tagmanager_mcp/server.py   # MCP Inspector
.venv/bin/python -m build                    # sdist + wheel into dist/ (gitignored)
.venv/bin/twine check dist/*                 # metadata + README renders on PyPI
```

Register the checkout (not the published version) with Claude Code:
`claude mcp add --scope user tagmanager-mcp -- <abs path>/.venv/bin/tagmanager-mcp`.
Restart Claude Code after code changes; tools load only at startup.

## Architecture

```
tagmanager_mcp/
├── coordinator.py   # mcp = FastMCP(...) — the one instance everything registers on
├── server.py        # importing the tools modules triggers @mcp.tool() → mcp.run() (stdio)
└── tools/
    ├── client.py    # ADC credential singleton (lazy, threading.Lock); fresh discovery
    │                # client per call. execute() is the mandatory layer for every API
    │                # call: backoff on 429/quota-403/5xx, 4s throttle after the first
    │                # rate limit, HttpError → actionable message, mutating=True for
    │                # writes. Also prevent_stdio_inheritance()
    ├── utils.py     # construct_*_path() (int / numeric string / full path), slim_*(),
    │                # merge_patch() (shallow, null deletes a key), paginate()
    ├── structure.py # list_accounts / list_containers / list_workspaces / get_workspace_status
    ├── tags.py      # list_tags (slim) / get_tag (full) / create / update / delete
    ├── triggers.py  # same shape as tags.py
    ├── variables.py # same shape as tags.py
    └── versions.py  # version reads (list/get/get_live) + create_version / publish_version.
                     # Versions are container-scoped, not under a workspace; create_version
                     # consumes the workspace; responses are always slimmed
```

```
.github/workflows/ci.yml       # push main / PR: nox tests (3.10–3.14 matrix) + lint (3.14)
.github/workflows/release.yml  # v* tag: tests → build → publish (OIDC)
noxfile.py                     # venv_backend='none' — sessions run on the current interpreter
.claude/settings.json          # project-level Bash allowlist (checked in)
```

Rules for changing code:

- New tools are `async def` wrapping the blocking call in
  `asyncio.to_thread(_sync)`. The docstring *is* the tool description; document
  accepted argument formats under `Args:`.
- Every API call goes through `client.execute()`; a direct `request.execute()`
  loses retries and error translation.
- `list_*` returns skeletons (`slim_*` in utils), `get_*` returns full detail.
  One GA4 event tag is hundreds of lines of JSON.
- Every list method goes through `paginate()`. The API omits array keys
  entirely when a list is empty, so read response fields with `.get()`.
- Annotations on every tool: reads `readOnlyHint=True`, create/update
  `destructiveHint=False`, delete `destructiveHint=True`. `create_version` and
  `publish_version` are also `destructiveHint=True` — one consumes the
  workspace, the other changes the live site.
- Three rules for writes: (1) write calls use `execute(request, mutating=True)`
  — rate limits are retried, 5xx is not, because the API has no idempotency key
  and a retry could duplicate the write; (2) update means "get current →
  `merge_patch` shallow merge (null deletes a key, lists replace wholesale) →
  submit with fingerprint", so the model sends only what it wants changed;
  (3) `delete_*` and `publish_version` require `confirm=True` and raise before
  touching the API without it.
- stdout belongs to the MCP protocol; logging and debug output go to stderr.

## Conventions

- black: line-length 80, skip-string-normalization (single quotes, see pyproject)
- Comments in English; type hints on functions; Python >= 3.10 (local venv 3.14)
- Tests: stdlib unittest (not pytest), `tests/*_test.py`, fully offline

## Hard constraints (each has a real incident behind it; do not relax)

- `mcp>=1.28,<2`: the v2.0 beta changed the API completely (MCPServer replaces
  FastMCP) and upstream asks for a `<2` pin. Official `mcp` package, not the
  third-party `fastmcp` 2.x.
- `cryptography<49`: 49+ ships no Intel-macOS wheels, and a source build fails
  on this machine (x86_64 Mac, no Rust toolchain).
- GTM quota: 0.25 QPS (25 requests per 100s window) + 10,000/day per GCP
  project; per-user overrides do nothing. Rate limiting returns 429 in practice
  (the official docs only mention 403 — `execute()` retries both). Never design
  a tool that fans out across containers.
- Return annotations must be `dict[str, Any]`; a bare `dict` produces no
  structured output schema.
- Built-in triggers (IDs 21474795xx: All Pages, Initialization, Consent Init)
  never appear in `list_triggers` — account for that in reference analysis.
- Fingerprint mismatch returns **400** `badRequest`, "The provided entity
  fingerprint is not valid." (measured 2026-07-07, undocumented). 412 was never
  observed but its branch stays as a fallback.
- Discovery facts (verified against the live discovery doc, 2026-07-08): method
  names are **snake_case** (`workspaces.create_version`, `versions.set_latest`);
  the collection is `version_headers`; `version_headers.list` returns its array
  under `containerVersionHeader`. Offline mocks cannot catch a misspelled
  method, but a real write is not needed to check: discovery methods are
  generated from the doc, so `hasattr(ws(), 'create_version')` verifies names
  and signatures with zero API calls.
- Scopes (measured): `create_version` needs `edit.containerversions`, **not**
  edit.containers — the reference page and the discovery doc summary disagree,
  trust the reference page; `publish` accepts `tagmanager.publish` only. But
  `versions.get` / `versions.live` / `version_headers.list` need **readonly**
  alone.
- Container version JSON is huge: the 211-tag test container returns **688KB**
  (~170k tokens). So `get_version` / `get_live_version` deliberately **deviate**
  from "get_* returns everything" and slim embedded entities (measured 75KB,
  9.1x). Version-header counters like numTags come back as **strings**, and
  zero-valued fields are omitted entirely, so `_slim` must test
  `if key in entity`.
- **PyPI releases are irreversible**: a version number is single-use once any
  file lands (deleting the release does not free it), and release metadata
  (`description`, README as long_description) cannot be edited after upload —
  only a new version fixes wording. So README / pyproject changes must land
  **before** the tag. Use `yank` (PEP 592), never delete; deleting frees the
  package name for someone else.
- End users install with `pipx install tagmanager-mcp` — it is an executable,
  not a library, and PEP 668 makes a bare `pip install` fail on system Python.
  Keep the README Setup section on pipx; `git clone` + `pip install -e .`
  belongs in a development section. Claude Desktop does not inherit shell PATH,
  so its config needs an absolute path.
- GTM has no "unpublish" API: **rollback = publish an older version**
  (`publish_version` works on any version). `set_latest_version` changes the
  sync baseline for new workspaces, not what is live — mistaking it for a
  rollback will cause an incident.

## Authentication (ADC)

Google hard-blocks gcloud's default OAuth client for tagmanager scopes ("This
app is blocked"), so a self-made Desktop OAuth client is required (GCP Console
→ Auth Platform → Clients → Desktop app; publish the consent screen to
production or refresh tokens expire after 7 days):

```bash
gcloud services enable tagmanager.googleapis.com --project=YOUR_PROJECT
gcloud auth application-default login \
  --client-id-file=YOUR_DESKTOP_CLIENT.json \
  --scopes=https://www.googleapis.com/auth/tagmanager.readonly,https://www.googleapis.com/auth/tagmanager.edit.containers,https://www.googleapis.com/auth/tagmanager.edit.containerversions,https://www.googleapis.com/auth/tagmanager.publish,https://www.googleapis.com/auth/cloud-platform
gcloud auth application-default set-quota-project YOUR_PROJECT
```

`cloud-platform` exists only so `set-quota-project` can validate. Scopes are
frozen at consent time and a re-login replaces the whole set, so re-request the
scopes of any other Google tooling sharing this ADC. Self-check (expects 200):

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  https://tagmanager.googleapis.com/tagmanager/v2/accounts
```

The actual GCP project, OAuth client file and test container IDs live in
Claude's project memory, not here — this file is public with the repo.

## Releasing (PyPI)

Distribution name `tagmanager-mcp`, Python module `tagmanager_mcp`, MCP server
name `tagmanager-mcp` in the README (a local dev registration may still use an
older key such as `gtm`). Releases happen entirely in CI; a local `dist/` is
for verification only and is **never** uploaded:

```bash
# Preconditions: main clean, nox green, all wording changes committed
git tag -a v0.3.0 -m "v0.3.0: ..."
git push origin v0.3.0     # runs release.yml: tests → build → publish
```

- **Auth is Trusted Publishing (OIDC); no API token exists in the repo.** The
  publisher configured on PyPI must match the workflow exactly: repo
  `jinchliu/tagmanager-mcp`, workflow file `release.yml`, environment `pypi`.
  Change one and PyPI's config must change too, or OIDC is rejected.
- Only the `publish` job holds `id-token: write`; the build never sees OIDC
  credentials.
- **The tests job inside `release.yml` is deliberate**: pushing a tag does not
  trigger `ci.yml`, so without it a red tree could ship. Do not delete it.
- A failed release does not burn the version number as long as no file was
  uploaded. Redo a tag with
  `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`.

## History and legacy API facts

- **v0.2, writes (2026-07-07)**: added `tagmanager.edit.containers` and 9 write
  tools. Legacy facts: delete methods **do not accept** a fingerprint;
  `workspaces.delete` needs `tagmanager.delete.containers` (not edit — hence no
  workspace management); free containers allow at most 3 concurrent workspaces,
  so never design a "temporary workspace per operation" flow.
- **v0.3, versions and publishing (verified end-to-end 2026-07-09)**: added
  `tagmanager.edit.containerversions` and `tagmanager.publish` (publish accepts
  only the latter). versions.py is separate to underline that editing a
  workspace ≠ going live. `create_version` consumes the workspace, returns
  newWorkspacePath and lifts compilerError/syncStatus to the top level for
  pre-publish checks; `publish_version` requires `confirm=True`. Version
  management (`update` / `delete` / `undelete` / `set_latest_version`) is not
  implemented — the existing scopes already cover it if wanted.

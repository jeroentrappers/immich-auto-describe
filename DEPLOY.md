# Deploying immich-auto-describe

Two components:

1. **Plugin** — a Wasm plugin loaded *inside* `immich-server` (fires on new uploads, writes the
   description). Installed by placing files in Immich's external-plugin folder + a restart.
2. **Sidecar** — a container running the model fleet. The plugin calls it over HTTP; it fetches
   the thumbnail from Immich and runs the VLM.

```
immich-server (plugin, Wasm) ──HTTP──► sidecar ──► VLM (local/cloud)
        ▲                                  │
        └──────── writes description ◄──────┘ (sidecar reads thumbnail from Immich API)
```

## Prerequisites

- Immich **v3+** (plugin/workflow system present).
- Ability to set **env vars** on the `immich-server` container and mount a volume.
- An Immich **API key** (Account Settings → API Keys). Read scope is enough for the live plugin
  path; **backfill** additionally needs asset **write**.
- At least one inference backend (local OpenAI-compatible server, e.g. Ollama/LM Studio/vLLM, or
  a cloud endpoint like OpenRouter/OpenAI).

---

## Step 1 — Build (or obtain) the plugin

```bash
# install the extism-js compiler once
curl -Ls https://raw.githubusercontent.com/extism/js-pdk/main/install.sh | bash
cd plugin && ./build.sh        # -> plugin/dist/plugin.wasm
```

You now have the two files the server needs: `plugin/manifest.json` and `plugin/dist/plugin.wasm`.

## Step 2 — Install the plugin into immich-server

External plugins are **disabled by default**. Enable them, point Immich at an install folder,
and drop the plugin there as a subfolder.

**a. Lay out the plugin folder** on the host (one subfolder per plugin):

```
/path/to/immich-plugins/
└── immich-auto-describe/
    ├── manifest.json
    └── dist/
        └── plugin.wasm
```

**b. Edit your Immich `docker-compose.yml`** (the `immich-server` service):

```yaml
services:
  immich-server:
    environment:
      IMMICH_ALLOW_EXTERNAL_PLUGINS: "true"
      IMMICH_PLUGINS_INSTALL_FOLDER: "/plugins"
    volumes:
      - /path/to/immich-plugins:/plugins:ro
```

**c. Restart** and confirm it imported:

```bash
docker compose up -d immich-server
docker compose logs -f immich-server | grep -i plugin      # look for the import log
# or via API:
curl -H "x-api-key: $IMMICH_API_KEY" http://<immich>/api/plugins | jq '.[].name'
# -> should include "immich-auto-describe"
```

## Step 3 — Deploy the sidecar

From this repo:

```bash
cp .env.example .env      # set IMMICH_API_KEY (+ any cloud key)
```

Edit `docker-compose.yml` here:
- set the `PROVIDERS` JSON (local and/or cloud — see README),
- set `IMMICH_URL` to the API reachable *from the sidecar container* (e.g.
  `http://immich-server:2283/api` on the Immich network),
- set the `networks:` block to your Immich compose network name (`docker network ls`).

```bash
docker compose up -d --build
curl localhost:8000/healthz      # provider health
```

**Networking:** the plugin's HTTP call originates from `immich-server`, so the sidecar must be
reachable from there — put the sidecar on the **same Docker network** as Immich and use its
service name (`http://immich-auto-describe:8000`). The sidecar in turn must reach the Immich API
(`IMMICH_URL`) and your model host(s).

## Step 4 — Create the workflow

In Immich → **Admin → Workflows** (or Plugins), create a workflow from the bundled
**`auto-describe-new-uploads`** template (trigger `AssetMetadataExtraction`), and set the
`describe` step config:

- `sidecarUrl`: `http://immich-auto-describe:8000`
- `language`: `en` (or `nl`, `de`, …)
- `overwriteExisting`: `false`

New uploads are now described automatically (existing descriptions are never overwritten unless
`overwriteExisting` is on).

## Step 5 — Backfill the existing library

The plugin only fires on new uploads. For everything already there (needs a **write** API key):

```bash
docker compose exec immich-auto-describe python -m app.backfill --type IMAGE
docker compose exec immich-auto-describe python -m app.backfill --type VIDEO
```

Resumable + idempotent (skips assets that already have a description unless `--overwrite`).

---

## Verify end-to-end

1. Upload a photo → within moments its **Description** (info panel / press `i`) shows an AI caption.
2. Search the caption text in Immich — it's full-text searchable.
3. `docker compose logs immich-auto-describe` shows the request; `/healthz` shows providers up.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Plugin not listed in `/api/plugins` | `IMMICH_ALLOW_EXTERNAL_PLUGINS` not `true`, wrong `IMMICH_PLUGINS_INSTALL_FOLDER`, or folder layout wrong (must be `<folder>/immich-auto-describe/{manifest.json,dist/plugin.wasm}`); restart server |
| Descriptions never appear | Workflow not created/enabled; `sidecarUrl` not reachable from `immich-server`; check server logs |
| Plugin HTTP blocked | Method needs `hostFunctions: true` + `allowedHosts` (already set in our manifest to `["*"]`; tighten to your sidecar host if desired) |
| `/healthz` shows a provider down | Wrong `base_url`/`model`/key; model host unreachable from the sidecar container |
| Backfill 403 on write | API key lacks asset write scope |

## Upgrade / uninstall

- **Upgrade plugin:** rebuild `plugin.wasm`, replace files in the install folder, restart `immich-server`.
- **Upgrade sidecar:** `docker compose pull && docker compose up -d --build`.
- **Uninstall:** remove the plugin subfolder + restart server; `docker compose down` the sidecar.
  Generated descriptions remain on assets (edit/clear them in Immich if desired).

## Security notes

- **Cloud egress:** if a `PROVIDERS` entry is a cloud endpoint, thumbnails + minimal context are
  sent there. Use local providers to keep everything on your network.
- **allowedHosts:** the manifest allows `["*"]` for flexibility; restrict it to your sidecar host
  for a tighter posture (requires a manifest edit + rebuild).
- **API key:** give the sidecar the least scope it needs (read for live; write only if backfilling).

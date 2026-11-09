# immich-auto-describe

Automatic **AI visual descriptions + tags** for your Immich library — photos *and* videos —
using a **local and/or cloud** vision model. Built as a native **Immich plugin** (event-driven,
no polling) plus a small **inference sidecar** that runs the model fleet.

Descriptions land in each asset's `description` field: searchable in Immich, exportable to
EXIF, editable, and screen-reader friendly. It **complements** CLIP smart-search and OCR (it
consumes date/location/people/OCR as context) rather than replacing them.

📦 **[Deployment guide → DEPLOY.md](DEPLOY.md)**

Related Immich discussions: [Auto visual descriptions (#29988)](https://github.com/immich-app/immich/discussions/29988) · [Plugin marketplace / easy install (#29998)](https://github.com/immich-app/immich/discussions/29998)

## How it works

```
Immich  ──AssetMetadataExtraction──►  auto-describe PLUGIN (Wasm, native)
                                             │  httpRequest → sidecar /describe {assetId}
                                             ▼
                                    SIDECAR (this repo)
                                     • fetch thumbnail / video-frame montage (Immich API)
                                     • run the VLM FLEET (local + cloud, self-healing)
                                     • add people/date/location as prompt context
                                             │  { description, tags }
                                             ▼
                          plugin writes description via workflow `changes`
```

Why the split? Immich's plugin host exposes `httpRequest` as **text-only** (binary-unsafe), so
a pure-Wasm plugin can't fetch pixels. The sidecar fetches the image; the plugin does the
native write-back. (A future upstream PR making `httpRequest` binary-safe would collapse this
into a single pure plugin — see [Roadmap](#roadmap).)

## Requirements

- A running Immich instance (plugin system / workflows enabled).
- An Immich **API key** (read is enough for the live plugin path; **write** is needed for backfill).
- At least one inference backend, either:
  - **Local** — Ollama / LM Studio / llama.cpp-server / vLLM serving an OpenAI-compatible API
    with a vision model (e.g. `qwen3-vl`, `gemma-3-vl`, `llava`), or
  - **Cloud** — any OpenAI-compatible endpoint (OpenRouter, OpenAI, Together, …). No GPU needed.

## 1. Run the sidecar

```bash
cp .env.example .env         # set IMMICH_API_KEY, provider(s), optional cloud keys
# edit docker-compose.yml -> PROVIDERS (local and/or cloud) + the immich network name
docker compose up -d --build
curl localhost:8000/healthz  # provider health
```

`PROVIDERS` is a JSON array — mix local and cloud freely:

```json
[
  {"name":"local","base_url":"http://host.docker.internal:1234/v1","model":"qwen/qwen3-vl-8b","concurrency":4,"max_dim":768},
  {"name":"openrouter","base_url":"https://openrouter.ai/api/v1","model":"qwen/qwen2.5-vl-7b-instruct","api_key_env":"OPENROUTER_API_KEY","concurrency":8,"max_dim":1024}
]
```

The fleet load-balances across providers (least-busy first), caps concurrency per provider,
and self-heals: a provider that fails repeatedly is benched for a cooldown and rejoins
automatically.

**Reasoning models in LM Studio** (Gemma 4, Qwen3 thinking, …) think before every caption,
and LM Studio's OpenAI endpoint ignores requests to turn that off. Use its native API instead:
`"api":"lmstudio"` (optional `"reasoning":"off"|"on"`, default `off`) — about 5× faster:

```json
{"name":"lmstudio","base_url":"http://host.docker.internal:1234","api":"lmstudio",
 "model":"gemma-4-e4b-it","concurrency":2,"max_dim":768}
```

## 2. Build & install the plugin

Prereqs: **Node.js** and the **`extism-js`** compiler:

```bash
curl -Ls https://raw.githubusercontent.com/extism/js-pdk/main/install.sh | bash   # installs extism-js (+ binaryen)
```

Then build (one command):

```bash
cd plugin
./build.sh          # -> dist/plugin.wasm
```

`build.sh` first builds the **vendored `@immich/plugin-sdk`** (it is *not* published to npm —
this repo vendors its source under `plugin/vendor/plugin-sdk`), then runs
`prepareBuild → esbuild → extism-js`. (On npm ≥ 12 you may need to approve esbuild's install
script once — `build.sh` does this automatically.)

Install the plugin (`plugin/manifest.json` + `plugin/dist/plugin.wasm`) via the Immich admin
**Plugins** page, then create a **workflow** from the bundled `auto-describe-new-uploads`
template (or add the `describe` method to your own), setting `sidecarUrl` to
`http://immich-auto-describe:8000` and your `language`. New uploads are described automatically.

## 3. Backfill the existing library

The plugin only fires on new uploads. For everything already there:

```bash
docker compose exec immich-auto-describe python -m app.backfill --type IMAGE
docker compose exec immich-auto-describe python -m app.backfill --type VIDEO
```

Newest first. To keep up with recent uploads without the plugin (e.g. from a timer), limit it
to assets uploaded in the last N days: `python -m app.backfill --since-days 7`.

Resumable, idempotent (skips assets that already have a description unless `--overwrite`),
and uses the whole fleet. Requires an Immich **write** key.

## Configuration (env)

| var | meaning |
|---|---|
| `IMMICH_URL` | Immich API base incl. `/api` (e.g. `http://immich-server:2283/api`) |
| `IMMICH_API_KEY` | Immich API key (read; write for backfill) |
| `PROVIDERS` | JSON array of OpenAI-compatible backends (see above) |
| `DEFAULT_LANG` | default output language (`en`, `nl`, …) |
| `VIDEO_FRAMES` | frames sampled per video for the montage (default 6) |
| `AI_PREFIX` | optional marker prefixed to generated text (e.g. `"[AI] "`) |
| `MAX_OUTPUT_TOKENS` | cap per description (default 800) |

## Roadmap

- **Pure plugin (no sidecar):** upstream PR to make the host `httpRequest` binary-safe
  (base64) so a Wasm plugin can fetch the thumbnail itself.
- **People context in payload:** when `AssetPersonV1` / `PersonRecognized` land, drop the
  sidecar's extra people lookup.
- Push detected objects into Immich **tags**; per-language prompt templates in the UI.

## License

AGPL-3.0-or-later (matches the Immich plugin ecosystem).

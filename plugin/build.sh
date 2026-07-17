#!/usr/bin/env bash
# Build dist/plugin.wasm. Prereqs: node/npm, and extism-js on PATH
#   (curl -Ls https://raw.githubusercontent.com/extism/js-pdk/main/install.sh | bash)
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

# @immich/plugin-sdk is NOT published to npm -> build the vendored copy once.
if [ ! -f vendor/plugin-sdk/dist/index.js ]; then
  ( cd vendor/plugin-sdk && npm install --no-audit --no-fund \
      && { npm install-scripts approve esbuild 2>/dev/null || true; } \
      && node esbuild.js )
fi

node vendor/plugin-sdk/dist/cli.js prepareBuild manifest.json   # -> dist/index.d.ts
node esbuild.js                                                  # -> dist/index.js
extism-js dist/index.js -i dist/index.d.ts -o dist/plugin.wasm   # -> dist/plugin.wasm
echo "built: $(ls -la dist/plugin.wasm)"

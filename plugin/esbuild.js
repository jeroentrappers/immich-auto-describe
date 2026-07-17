// Bundle src/index.ts -> dist/index.js for extism-js (quickjs/cjs, es2020).
// Uses the vendored @immich/plugin-sdk (not published to npm) via an alias.
const path = require('path');
const esbuild = require('./vendor/plugin-sdk/node_modules/esbuild');

esbuild.build({
  entryPoints: ['src/index.ts'],
  outdir: 'dist',
  bundle: true,
  sourcemap: false,
  minify: false,
  format: 'cjs',
  target: ['es2020'],
  alias: {
    '@immich/plugin-sdk': path.resolve(__dirname, 'vendor/plugin-sdk/dist/index.js'),
  },
}).then(() => console.log('esbuild: dist/index.js')).catch((e) => { console.error(e); process.exit(1); });

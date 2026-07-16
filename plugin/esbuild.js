const esbuild = require('esbuild');

esbuild.build({
  entryPoints: ['src/index.ts'],
  outdir: 'dist',
  bundle: true,
  sourcemap: false,
  minify: false,
  format: 'cjs', // extism-js / quickjs needs CJS
  target: ['es2020'], // quickjs ceiling
});

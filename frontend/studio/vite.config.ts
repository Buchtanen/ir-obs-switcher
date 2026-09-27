import { defineConfig } from 'vite';

export default defineConfig({
  base: '/studio/',
  build: { outDir: '../../src/irswitch/web/studio', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:17321' } },
});

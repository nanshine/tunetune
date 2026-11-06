import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  // Built assets ship inside the shared skill so every skill installer delivers the panel.
  build: {
    outDir: '../plugins/tunetune/skills/research-workspace/assets/panel',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (proxyRequest, request) => {
            if (request.headers.origin === `http://${request.headers.host}`) {
              proxyRequest.setHeader('Origin', 'http://127.0.0.1:8765');
            }
          });
        },
      },
    },
  },
});

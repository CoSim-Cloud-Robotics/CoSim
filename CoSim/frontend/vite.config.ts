import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://api-gateway:8000',
        changeOrigin: true,
        // Strip the /api prefix so requests keep their existing version segment (e.g. /v1/projects)
        rewrite: path => path.replace(/^\/api/, '')
      },
      '/simulations': {
        target: 'http://simulation-agent:8005',
        changeOrigin: true,
        ws: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
});

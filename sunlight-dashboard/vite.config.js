import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.SUNLIGHT_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/v2': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/dashboard/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/admin': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/analyze': { target: apiTarget, changeOrigin: true },
      '/batch': { target: apiTarget, changeOrigin: true },
      '/profiles': { target: apiTarget, changeOrigin: true },
      '/assurance': { target: apiTarget, changeOrigin: true },
      '/docs': { target: apiTarget, changeOrigin: true },
      '/openapi.json': { target: apiTarget, changeOrigin: true },
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});

import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/ws": {
        target: process.env.VITE_VOICE_WS_BASE ?? "http://localhost:8003",
        ws: true,
        changeOrigin: true,
      },
      "/v1": {
        target: process.env.VITE_API_BASE ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
}));

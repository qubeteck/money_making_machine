import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const BACKEND = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

  return {
    base: "/ui/",
    plugins: [react(), tailwindcss()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": { target: BACKEND, changeOrigin: false },
        "/auth": { target: BACKEND, changeOrigin: false },
        "/health": { target: BACKEND, changeOrigin: false },
        "/metrics": { target: BACKEND, changeOrigin: false },
        "/v1": { target: BACKEND, changeOrigin: false },
        "/ws": { target: BACKEND.replace(/^http/, "ws"), ws: true, changeOrigin: false },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      chunkSizeWarningLimit: 1200,
    },
  };
});

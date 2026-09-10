import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      // The backend serves /health, /auth/login, /queue, /cases/... at the
      // root. The console prefixes its calls with /api so the dev server can
      // tell them apart from its own routes, so the prefix is stripped here.
      "/api": {
        // 127.0.0.1, not "localhost": on Windows "localhost" resolves to ::1
        // first, and uvicorn bound to 127.0.0.1 is not listening there. The
        // request then hangs until timeout instead of failing fast.
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // No rewrite: the backend route really is /ws/session/{id}.
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});

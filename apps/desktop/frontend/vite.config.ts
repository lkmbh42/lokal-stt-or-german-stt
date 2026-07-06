/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-only proxy: `npm run dev` talks to a locally running backend.
// Production build is served by FastAPI itself (same origin, no proxy).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8710",
      "/ws": { target: "ws://127.0.0.1:8710", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run dev` proxies the API to `python -m omen serve` (port 8765).
const API = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(["/agent", "/threads", "/ui", "/personas", "/health"].map((p) => [p, API])),
  },
  test: {
    environment: "node",
  },
});

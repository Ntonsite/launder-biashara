import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs separately; proxy keeps the browser on one origin (no CORS, same paths as production nginx).
const api = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": api, "/media": api } },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});

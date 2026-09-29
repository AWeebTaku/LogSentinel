import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API serves ui/dist itself (python -m logsentinel.api), so production needs no proxy.
// For `npm run dev` the app talks to http://127.0.0.1:8000 directly (CORS allows localhost:5173).
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 2500 },
  test: { environment: "node" },
});

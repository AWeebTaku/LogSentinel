import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API serves ui/dist itself (python -m logsentinel.api), so production needs no proxy.
// For `npm run dev` the app talks to http://127.0.0.1:8000 directly (CORS allows localhost:5173).
//
// Three HTML entries share one build: index.html (operator -- Dashboard+Alerts, the day-to-day
// production view), admin.html (the full testing/training suite on top), and playground.html (the
// standalone personal test-tool portal, one page, no nav). They share chunks; which ones are
// actually reachable is an API-side concern (LOGSENTINEL_APP_MODE gates the routes and which file
// gets served at "/"), not a separate frontend build.
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 2500,
    rollupOptions: { input: { index: "index.html", admin: "admin.html", playground: "playground.html" } },
  },
  css: {
    // Carbon's own SCSS still uses the legacy if() syntax; silence that
    // upstream deprecation noise instead of waiting on a Carbon release.
    preprocessorOptions: { scss: { silenceDeprecations: ["if-function"] } },
  },
  test: { environment: "node" },
});

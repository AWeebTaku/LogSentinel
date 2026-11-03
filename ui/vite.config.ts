import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API serves ui/dist itself (python -m logsentinel.api), so production needs no proxy.
// For `npm run dev` the app talks to http://127.0.0.1:8000 directly (CORS allows localhost:5173).
//
// Two HTML entries share one build: index.html (operator -- Dashboard+Alerts, the day-to-day
// production view) and admin.html (the full testing/training suite on top). They share chunks;
// splitting them is an API-side concern (LOGSENTINEL_APP_MODE=operator refuses the admin routes
// and the operator deployment doesn't ship admin.html), not a separate frontend build.
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 2500,
    rollupOptions: { input: { index: "index.html", admin: "admin.html" } },
  },
  css: {
    // Carbon's own SCSS still uses the legacy if() syntax; silence that
    // upstream deprecation noise instead of waiting on a Carbon release.
    preprocessorOptions: { scss: { silenceDeprecations: ["if-function"] } },
  },
  test: { environment: "node" },
});

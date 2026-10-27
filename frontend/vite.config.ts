import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Only the build-time env is read here; avoids pulling in the full Node typings for one variable.
declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  // Served under a sub-path behind a shared reverse proxy (e.g. /sbi-relationship-crm/): set at build time.
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8010",
        changeOrigin: true,
      },
    },
  },
});

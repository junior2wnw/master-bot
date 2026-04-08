import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Mini App is served by FastAPI under /app, so production asset URLs
  // must stay under that mount point instead of the domain root.
  base: "/app/",
  plugins: [react()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
});

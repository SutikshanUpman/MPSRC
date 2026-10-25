import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The production build is emitted into ../web, which server.py serves, so the console ships
// without a separate web server (and without node at run time).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../web",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000" },
    },
  },
});

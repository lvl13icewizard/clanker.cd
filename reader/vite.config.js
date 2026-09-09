import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// The personal reader serves the same public/ the engine writes into, so a
// press is visible here the moment it lands. Nothing is snapshotted. The
// app source itself lives in ../site/reader (shared with the demo personas).
export default defineConfig({
  plugins: [react()],
  publicDir: "../site/public",
  server: { fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] } },
});

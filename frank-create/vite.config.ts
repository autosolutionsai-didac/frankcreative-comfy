import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const comfyTarget = "http://127.0.0.1:8188";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": comfyTarget,
      "/frank": comfyTarget,
      "/view": comfyTarget,
      "/upload": comfyTarget,
      "/ws": {
        target: comfyTarget.replace("http", "ws"),
        ws: true
      }
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts"
  }
});

import { cwd } from "node:process";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, cwd(), "");
  const backendUrl = env.VITE_BACKEND_URL || "http://127.0.0.1:18101";

  return {
    plugins: [react()],
    server: {
      port: 18174,
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: false,
        },
      },
    },
  };
});

import { defineConfig } from "vite";

export default defineConfig({
  root: "web",
  build: {
    outDir: "../web_dist",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "^/api/": "http://127.0.0.1:8790",
    },
  },
});

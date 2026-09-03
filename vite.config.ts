import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Vite configuration for the VS Code Webview.
// The webview source is in src/webview/ and the build outputs to dist/webview/
const webviewRoot = resolve(__dirname, "src", "webview");

export default defineConfig({
  root: webviewRoot,
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@": webviewRoot
    }
  },
  build: {
    outDir: resolve(__dirname, "dist", "webview"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(webviewRoot, "index.html"),
      output: {
        // Single bundle, no code splitting (CSP-friendly for VS Code webviews)
        manualChunks: undefined
      }
    },
    target: "es2020",
    sourcemap: true,
    minify: "esbuild"
  },
  server: {
    port: 3000,
    strictPort: true
  }
});

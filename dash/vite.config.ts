import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    target: "esnext",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("lightweight-charts")) return "charts"
          if (id.includes("react-dom") || id.includes("/react/")) return "vendor-react"
          if (id.includes("zustand") || id.includes("@tanstack/react-query")) return "vendor-state"
        },
      },
    },
  },
  optimizeDeps: {
    include: ["lightweight-charts"],
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/health": "http://127.0.0.1:8765",
      "/rounds": "http://127.0.0.1:8765",
      "/session": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
})

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Anfragen an /api gehen an das Python-Backend (uvicorn auf Port 8010;
// 8000 ist auf diesem Rechner schon vom Bewerbungs-Tool belegt)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8010" },
  },
});

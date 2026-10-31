import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import pkg from "./package.json";
import { userscriptCode } from "./src/oddsportalScripts";

// Tampermonkey-Skript als dist/handball-xg.user.js – das Backend liefert es unter /handball-xg.user.js aus.
// Die Bauzeit in der Versionsnummer sorgt dafür, dass Tampermonkey nach jedem Neubau aktualisiert.
function userscript(): Plugin {
  return {
    name: "handball-xg-userscript",
    apply: "build",
    generateBundle() {
      const stamp = new Date().toISOString().slice(0, 16).replace(/\D/g, "");
      this.emitFile({ type: "asset", fileName: "handball-xg.user.js", source: userscriptCode("http://127.0.0.1:8011", `${pkg.version}.${stamp}`) });
    },
  };
}

// Anfragen an /api gehen an das Python-Backend (uvicorn auf Port 8011;
// 8000 ist auf diesem Rechner schon vom Bewerbungs-Tool belegt)
export default defineConfig({
  plugins: [react(), userscript()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8011" },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dezvoltare, /api merge catre backend-ul Python (python -m etabs_beams serve)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
});

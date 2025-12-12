import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// Backend URL from environment, set by ChatkitDemoLauncher
const backendUrl = process.env.CHATKIT_BACKEND_URL ?? "http://127.0.0.1:8000";
const agencyName = process.env.CHATKIT_AGENCY_NAME ?? "agency";

export default defineConfig({
  plugins: [react()],
  define: {
    // Pass agency name to the frontend
    "import.meta.env.VITE_AGENCY_NAME": JSON.stringify(agencyName),
  },
  server: {
    port: parseInt(process.env.CHATKIT_FRONTEND_PORT ?? "3000"),
    host: "0.0.0.0",
    proxy: {
      "/chatkit": {
        target: backendUrl,
        changeOrigin: true,
        rewrite: (path) => `/${agencyName}${path}`,
      },
    },
  },
});

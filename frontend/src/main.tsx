import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

createRoot(document.getElementById("root")!).render(<App />);

// PWA service-worker registration.
//
// Only in production: Vite's HMR conflicts with a live SW during dev,
// and the SW would cache dev-mode assets that vanish on reload. The SW
// itself never caches /api/* — auth and payslip figures stay live.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch((err) => {
        // Non-fatal: the app works without SW, just no offline shell.
        console.warn("SW registration failed", err);
      });
  });
}

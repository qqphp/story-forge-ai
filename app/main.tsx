import { createRoot } from "react-dom/client";
import Home from "./page";
import "./globals.css";
import "./features/settings/video-settings.css";
import "./features/voices/voice-center.css";

if (import.meta.env.DEV && "serviceWorker" in navigator) {
  void navigator.serviceWorker.getRegistrations().then(async (registrations) => {
    const rootRegistrations = registrations.filter((registration) => {
      const scope = new URL(registration.scope);
      return scope.origin === location.origin && scope.pathname === "/";
    });
    const removed = await Promise.all(rootRegistrations.map((registration) => registration.unregister()));
    if (removed.some(Boolean)) location.reload();
  }).catch(() => {});
}

createRoot(document.getElementById("root")!).render(<Home />);

import { createRoot } from "react-dom/client";
import Home from "./page";
import "./globals.css";
import "./features/settings/video-settings.css";

createRoot(document.getElementById("root")!).render(<Home />);

import type { Metadata } from "next";
import "./globals.css";
import "./features/settings/video-settings.css";
import "./features/publishing/publishing.css";

export const metadata: Metadata = {
  title: "砚界 · StoryForge AI",
  description: "从一本书到分享文案、配音、封面与视频的全自动创作工作流。",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}

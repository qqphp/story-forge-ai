import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "砚界 · StoryForge AI",
  description: "从一本书到分享文案、配音、封面与视频的全自动创作工作流。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}

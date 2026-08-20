import type { PublishPlatform } from "@/app/features/shared/types";

export type PublishPlatformDefinition = {
  id: PublishPlatform;
  name: string;
  mark: string;
  hint: string;
  url: string;
};

export const publishPlatforms: PublishPlatformDefinition[] = [
  { id: "douyin", name: "抖音", mark: "音", hint: "视频、标题、简介、话题与封面", url: "https://creator.douyin.com/creator-micro/content/upload" },
  { id: "kuaishou", name: "快手", mark: "快", hint: "视频、标题、描述与话题", url: "https://cp.kuaishou.com/article/publish/video" },
  { id: "bilibili", name: "哔哩哔哩", mark: "B", hint: "视频、标题、简介与标签", url: "https://member.bilibili.com/platform/upload/video/frame" },
  { id: "xiaohongshu", name: "小红书", mark: "红", hint: "视频、标题、正文与话题", url: "https://creator.xiaohongshu.com/publish/publish?source=storyforge" },
  { id: "baijiahao", name: "百家号", mark: "百", hint: "视频、标题、正文与话题", url: "https://baijiahao.baidu.com/builder/rc/home" },
];

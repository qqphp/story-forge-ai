globalThis.StoryForgePlatforms={
  douyin:{label:"抖音",mark:"音",uploadUrl:"https://creator.douyin.com/creator-micro/content/upload"},
  kuaishou:{label:"快手",mark:"快",uploadUrl:"https://cp.kuaishou.com/article/publish/video"},
  bilibili:{label:"哔哩哔哩",mark:"B",uploadUrl:"https://member.bilibili.com/platform/upload/video/frame"},
  xiaohongshu:{label:"小红书",mark:"红",uploadUrl:"https://creator.xiaohongshu.com/publish/publish?source=storyforge"},
  baijiahao:{label:"百家号",mark:"百",uploadUrl:"https://baijiahao.baidu.com/builder/rc/home"},
};

globalThis.StoryForgePlatforms.openUrl=(platform,taskId)=>{
  const target=new URL(globalThis.StoryForgePlatforms[platform].uploadUrl);target.searchParams.set("storyforge_task",taskId);return target.href;
};

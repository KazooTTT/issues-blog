export interface ToolItem {
  name: string;
  description: string;
  href?: string;
  iconDomain?: string;
}

export interface ToolGroup {
  title: string;
  eyebrow: string;
  items: ToolItem[];
}

export const softwareGroups: ToolGroup[] = [
  {
    title: "开发",
    eyebrow: "BUILD",
    items: [
      { name: "Codex", description: "AI 编程助手", href: "https://openai.com/codex/" },
    ],
  },
  {
    title: "设计与记录",
    eyebrow: "CREATE",
    items: [
      { name: "Figma", description: "界面与产品设计", href: "https://www.figma.com/" },
      { name: "Canva", description: "平面设计", href: "https://www.canva.com/" },
      { name: "Shottr", description: "截图与标注", href: "https://shottr.cc/" },
      { name: "OBS Studio", description: "直播与录制", href: "https://obsproject.com/" },
    ],
  },
  {
    title: "浏览与笔记",
    eyebrow: "THINK",
    items: [
      { name: "Dia Browser", description: "AI 浏览器", href: "https://www.diabrowser.com/" },
      { name: "Google Chrome", description: "网页浏览器", href: "https://www.google.com/chrome/" },
      { name: "Obsidian", description: "本地知识库", href: "https://obsidian.md/" },
      { name: "Flomo", description: "快速笔记", href: "https://flomoapp.com/" },
    ],
  },
  {
    title: "效率",
    eyebrow: "FLOW",
    items: [
      { name: "1Password", description: "密码管理", href: "https://1password.com/" },
      { name: "Raindrop.io", description: "书签管理", href: "https://raindrop.io/" },
      { name: "n8n", description: "工作流自动化", href: "https://n8n.io/" },
      { name: "Follow", description: "RSS 阅读器", href: "https://app.follow.is/" },
      { name: "滴答清单", description: "任务管理", href: "https://dida365.com/" },
    ],
  },
  {
    title: "音乐",
    eyebrow: "MUSIC",
    items: [
      { name: "Apple Music", description: "音乐流媒体", href: "https://music.apple.com/" },
      { name: "网易云音乐", description: "音乐平台", href: "https://music.163.com/" },
    ],
  },
  {
    title: "阅读",
    eyebrow: "READING",
    items: [
      { name: "微信读书", description: "阅读平台", href: "https://weread.qq.com/" },
    ],
  },
  {
    title: "健康与运动",
    eyebrow: "HEALTH",
    items: [
      { name: "AutoSleep", description: "睡眠追踪", href: "https://autosleepapp.tantsissa.com/" },
      { name: "Garmin Connect", description: "运动与健康数据", href: "https://connect.garmin.com/" },
      { name: "Keep", description: "健身应用", href: "https://www.gotokeep.com/" },
    ],
  },
];

export const deviceGroups: ToolGroup[] = [
  {
    title: "电脑",
    eyebrow: "COMPUTING",
    items: [
      { name: "MacBook Air M4", description: "移动办公 · 16GB / 512GB", iconDomain: "apple.com" },
      { name: "Mac mini M2 Pro", description: "主力机 · 32GB / 512GB", iconDomain: "apple.com" },
      { name: "MacBook Air M1", description: "备用机 · 16GB / 256GB", iconDomain: "apple.com" },
      { name: "机械师整机", description: "Windows 台式机 · i5 / 32GB / 512GB", iconDomain: "microsoft.com/windows" },
    ],
  },
  {
    title: "移动设备",
    eyebrow: "MOBILE",
    items: [
      { name: "iPhone 13", description: "手机 · 256GB", iconDomain: "apple.com/iphone" },
      { name: "vivo X200 Pro mini", description: "手机", iconDomain: "vivo.com.cn" },
      { name: "iPad mini 5", description: "平板电脑", iconDomain: "apple.com/ipad" },
    ],
  },
  {
    title: "阅读设备",
    eyebrow: "READING",
    items: [
      { name: "Kindle Paperwhite 4", description: "电子阅读器", iconDomain: "kindle.com" },
      { name: "文石 Leaf5", description: "电子阅读器", iconDomain: "boox.com" },
    ],
  },
  {
    title: "穿戴与音频",
    eyebrow: "WEARABLE",
    items: [
      { name: "Apple Watch S9", description: "智能手表", iconDomain: "apple.com/watch" },
      { name: "佳明 Forerunner 265", description: "运动手表", iconDomain: "garmin.com" },
      { name: "AirPods Pro 2", description: "无线耳机", iconDomain: "apple.com/airpods" },
    ],
  },
  {
    title: "LUMIX M43",
    eyebrow: "CAMERA 01",
    items: [
      { name: "LUMIX GX9", description: "相机", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "LUMIX G9M2", description: "相机", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "LUMIX 14–140mm", description: "变焦镜头", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "LUMIX DG 15mm", description: "定焦镜头", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "LUMIX 25mm", description: "定焦镜头", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "LUMIX 100–300mm", description: "长焦镜头", iconDomain: "panasonic.com/global/consumer/lumix" },
      { name: "永诺 42.5mm", description: "定焦镜头", iconDomain: "yongnuo.com.cn" },
    ],
  },
  {
    title: "LUMIX 全画幅",
    eyebrow: "CAMERA 02",
    items: [
      { name: "LUMIX S9 + 18–40mm", description: "相机套机", iconDomain: "panasonic.com/global/consumer/lumix" },
    ],
  },
  {
    title: "随身影像",
    eyebrow: "CAMERA 03",
    items: [
      { name: "DJI Action 5 Pro", description: "运动相机", iconDomain: "dji.com" },
      { name: "DJI Osmo 360", description: "全景相机", iconDomain: "dji.com" },
      { name: "三星 ST90", description: "十多年前买的 CCD", iconDomain: "samsung.com" },
    ],
  },
];

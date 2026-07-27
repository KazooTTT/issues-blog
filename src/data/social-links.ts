export interface SocialLink {
  label: string;
  handle: string;
  href: string;
  icon: string;
  external?: boolean;
}

export const socialLinks: SocialLink[] = [
  {
    label: "Email",
    handle: "work@kazoottt.top",
    href: "mailto:work@kazoottt.top",
    icon: "email",
  },
  {
    label: "GitHub",
    handle: "KazooTTT",
    href: "https://github.com/KazooTTT",
    icon: "github",
    external: true,
  },
  {
    label: "X / Twitter",
    handle: "@KazooTTT",
    href: "https://x.com/KazooTTT",
    icon: "x",
    external: true,
  },
  {
    label: "Telegram",
    handle: "kazootttmemos",
    href: "https://t.me/kazootttmemos",
    icon: "telegram",
    external: true,
  },
  {
    label: "YouTube",
    handle: "@kazoottt255",
    href: "https://www.youtube.com/@kazoottt255",
    icon: "youtube",
    external: true,
  },
  {
    label: "Unsplash",
    handle: "@kazoottt",
    href: "https://unsplash.com/@kazoottt",
    icon: "unsplash",
    external: true,
  },
  {
    label: "微博",
    handle: "KazooTTT",
    href: "https://weibo.com/u/7796753876",
    icon: "weibo",
    external: true,
  },
  {
    label: "RSS",
    handle: "订阅文章",
    href: "/rss.xml",
    icon: "rss",
  },
];

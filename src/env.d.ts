/// <reference types="astro/client" />

import type { D1Binding } from "@/data/workout-store";

declare global {
  namespace App {
    interface Locals {
      // Cloudflare adapter 注入的运行时环境，静态构建时不存在。
      runtime?: {
        env: {
          DB?: D1Binding;
        };
      };
    }
  }
}

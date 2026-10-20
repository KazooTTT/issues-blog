#!/usr/bin/env node
/**
 * 把 `astro build` 的 Workers 风格产物（dist/client + dist/server）整理成
 * Cloudflare Pages 的 advanced mode 目录：
 *
 *   dist/pages/            静态资源（原 dist/client）
 *   dist/pages/_worker.js/ SSR 入口（原 dist/server，入口重命名为 index.js）
 *
 * @astrojs/cloudflare v14 只输出 Workers 布局，不再生成 `_worker.js`，
 * 因此部署到 Pages 前需要这一步转换。
 */
import { cp, mkdir, rename, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

const dist = new URL("../dist/", import.meta.url).pathname;
const clientDir = join(dist, "client");
const serverDir = join(dist, "server");
const outDir = join(dist, "pages");

if (!existsSync(clientDir) || !existsSync(serverDir)) {
  console.error("缺少 dist/client 或 dist/server，请先执行 `pnpm build`。");
  process.exit(1);
}

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

await cp(clientDir, outDir, { recursive: true });

const workerDir = join(outDir, "_worker.js");
await mkdir(workerDir, { recursive: true });
await cp(serverDir, workerDir, { recursive: true });

await rename(join(workerDir, "entry.mjs"), join(workerDir, "index.js"));
await rm(join(workerDir, "wrangler.json"), { force: true });
await rm(join(workerDir, "entry.mjs.map"), { force: true });

console.log(`Pages 部署目录已生成：${outDir}`);

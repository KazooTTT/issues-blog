import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { parseWishlistNote } from "../src/wishlist/import";

const { values } = parseArgs({
  options: {
    file: { type: "string" },
    owner: { type: "string", default: "KazooTTT" },
    project: { type: "string" },
    apply: { type: "boolean", default: false },
  },
});
if (!values.file)
  throw new Error(
    "Usage: pnpm exec tsx scripts/import-wishlist.ts --file <note.md> [--project <number> --apply]",
  );
const wishes = parseWishlistNote(readFileSync(values.file, "utf8"));
if (!values.apply) {
  console.log(
    JSON.stringify(
      { mode: "preview", count: wishes.length, items: wishes },
      null,
      2,
    ),
  );
} else {
  if (!values.project || !/^[1-9]\d*$/.test(values.project))
    throw new Error("--project is required with --apply");
  function gh<T>(args: string[]): T {
    return JSON.parse(
      execFileSync("gh", args, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }),
    );
  }
  const number = values.project;
  const owner = values.owner!;
  const project = gh<{ id: string }>([
    "project",
    "view",
    number,
    "--owner",
    owner,
    "--format",
    "json",
  ]);
  interface Field {
    id: string;
    name: string;
    options?: { id: string; name: string }[];
  }
  let fields = gh<{ fields: Field[] }>([
    "project",
    "field-list",
    number,
    "--owner",
    owner,
    "--limit",
    "100",
    "--format",
    "json",
  ]).fields;
  const definitions = [
    { name: "类型", type: "SINGLE_SELECT", options: "想买,想做,其他" },
    { name: "分类", type: "TEXT" },
    { name: "优先级", type: "SINGLE_SELECT", options: "高,中,低" },
    { name: "预算", type: "NUMBER" },
    { name: "目标日期", type: "DATE" },
  ];
  for (const field of definitions) {
    if (fields.some((existing) => existing.name === field.name)) continue;
    const args = [
      "project",
      "field-create",
      number,
      "--owner",
      owner,
      "--name",
      field.name,
      "--data-type",
      field.type,
      "--format",
      "json",
    ];
    if (field.options) args.push("--single-select-options", field.options);
    gh(args);
  }
  fields = gh<{ fields: Field[] }>([
    "project",
    "field-list",
    number,
    "--owner",
    owner,
    "--limit",
    "100",
    "--format",
    "json",
  ]).fields;
  const status = fields.find((field) =>
    ["Status", "状态"].includes(field.name),
  );
  const kinds = fields.find((field) => field.name === "类型");
  const category = fields.find((field) => field.name === "分类");
  const pending = status?.options?.find((option) =>
    ["Todo", "To do", "待实现"].includes(option.name),
  );
  const done = status?.options?.find((option) =>
    ["Done", "已实现", "已完成"].includes(option.name),
  );
  if (!status || !pending || !done || !kinds || !category)
    throw new Error(
      "Expected Status (Todo/Done or 待实现/已实现), 类型 and 分类 fields.",
    );
  const options = { buy: "想买", do: "想做", other: "其他" };
  for (const name of Object.values(options))
    if (!kinds.options?.some((option) => option.name === name))
      throw new Error(`Missing 类型 option: ${name}`);
  const existing = gh<{
    items: { id: string; title: string }[];
    totalCount: number;
  }>([
    "project",
    "item-list",
    number,
    "--owner",
    owner,
    "--limit",
    "2000",
    "--format",
    "json",
  ]);
  if (existing.totalCount > existing.items.length)
    throw new Error("Project too large for safe duplicate detection.");
  const titles = new Set(existing.items.map((item) => item.title));
  let created = 0;
  for (const wish of wishes) {
    if (titles.has(wish.title)) continue;
    const item = gh<{ id: string }>([
      "project",
      "item-create",
      number,
      "--owner",
      owner,
      "--title",
      wish.title,
      "--body",
      wish.description,
      "--format",
      "json",
    ]);
    function edit(fieldId: string, flag: string, value: string) {
      execFileSync(
        "gh",
        [
          "project",
          "item-edit",
          "--id",
          item.id,
          "--project-id",
          project.id,
          "--field-id",
          fieldId,
          flag,
          value,
        ],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
    }
    edit(
      status.id,
      "--single-select-option-id",
      wish.status === "done" ? done.id : pending.id,
    );
    edit(
      kinds.id,
      "--single-select-option-id",
      kinds.options!.find((option) => option.name === options[wish.kind])!.id,
    );
    if (wish.category) edit(category.id, "--text", wish.category);
    titles.add(wish.title);
    created++;
  }
  console.log(
    `Imported ${created} wishes; skipped ${wishes.length - created} existing titles.`,
  );
}

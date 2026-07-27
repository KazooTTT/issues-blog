import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import {
  mergeWorkouts,
  normalizeGarminActivities,
} from "../src/data/garmin-workouts";
import { normalizeWorkouts } from "../src/data/workouts";

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

const inputPath = argument("--input");
const outputPath = resolve(
  argument("--output") ?? "src/data/workouts.json",
);
const source = inputPath
  ? await readFile(resolve(inputPath), "utf8")
  : await readStdin();

if (!source.trim()) {
  throw new Error("Provide workout JSON through --input or stdin");
}

const incoming = process.argv.includes("--garmin")
  ? normalizeGarminActivities(JSON.parse(source))
  : normalizeWorkouts(JSON.parse(source));
const workouts = process.argv.includes("--merge")
  ? mergeWorkouts(
      normalizeWorkouts(JSON.parse(await readFile(outputPath, "utf8"))),
      incoming,
    )
  : incoming;
await writeFile(outputPath, `${JSON.stringify(workouts, null, 2)}\n`, "utf8");
console.log(`Synced ${workouts.length} workouts to ${outputPath}`);

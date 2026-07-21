import { cp, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

await mkdir(".next/standalone/.next", { recursive: true });
await cp(".next/static", ".next/standalone/.next/static", { recursive: true, force: true });
if (existsSync("public")) {
  await cp("public", ".next/standalone/public", { recursive: true, force: true });
}


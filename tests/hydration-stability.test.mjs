import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const workflowList = readFileSync(new URL("../app/features/workflows/WorkflowList.tsx", import.meta.url), "utf8");
const seedTasks = page.match(/const seedTasks:[\s\S]*?\n\];/)?.[0] ?? "";

test("server-rendered sample task timestamps are deterministic during hydration", () => {
  assert.doesNotMatch(
    seedTasks,
    /created_at\s*:\s*Math\.floor\(Date\.now\(\)\s*\/\s*1000\)/,
    "module-level sample timestamps must not depend on the server/client render time",
  );
});

test("server-rendered workflow dates use a shared deterministic formatter", () => {
  assert.match(workflowList, /formatShanghaiShortDate\(task\.created_at\)/);
  assert.match(workflowList, /formatShanghaiDateTime\(task\.created_at\)/);
  assert.doesNotMatch(workflowList, /toLocale(?:Date)?String/);
});

import assert from "node:assert/strict";
import test from "node:test";
import { formatShanghaiDateTime, formatShanghaiShortDate } from "../app/lib/date.ts";

test("workflow dates use Shanghai time independently of the host timezone", () => {
  assert.equal(formatShanghaiShortDate(0), "1月1日");
  assert.equal(formatShanghaiDateTime(0), "1970/1/1 08:00:00");
  const midnight = Date.UTC(2026, 9, 19, 16) / 1000;
  assert.equal(formatShanghaiShortDate(midnight), "10月20日");
  assert.equal(formatShanghaiDateTime(midnight), "2026/10/20 00:00:00");
});

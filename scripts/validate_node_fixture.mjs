#!/usr/bin/env node
/** Lint, test, and build the executable Node.js fixture in isolation. */

import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("..", import.meta.url));
const temporaryRoot = mkdtempSync(join(tmpdir(), "project-toolkit-node-fixture-"));
const fixture = join(temporaryRoot, "node");

function run(command, args) {
  console.log("+", command, ...args, `(cwd=${fixture})`);
  const result = spawnSync(command, args, { cwd: fixture, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} failed with status ${result.status ?? 1}`);
  }
}

try {
  cpSync(join(root, "tests/fixtures/node"), fixture, { recursive: true });
  run("npm", ["run", "lint"]);
  run("npm", ["test"]);
  run("npm", ["run", "build"]);
  console.log("node fixture: OK");
} finally {
  rmSync(temporaryRoot, { recursive: true, force: true });
}

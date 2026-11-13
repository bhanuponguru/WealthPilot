// Validate every ```mermaid block in the Markdown docs with the real Mermaid parser (the MkDocs build does NOT check diagram syntax).
//
// Mermaid and jsdom are not project dependencies. Install them anywhere, then point this script at that folder:
//
//   mkdir -p /tmp/mmd && cd /tmp/mmd && npm init -y && npm install mermaid@11 jsdom@25
//   MERMAID_DIR=/tmp/mmd node scripts/check_mermaid.mjs docs
//
// Exit code 1 if any diagram fails to parse.

import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { createRequire } from "module";

const modDir = process.env.MERMAID_DIR;
if (!modDir) {
  console.error("Set MERMAID_DIR to a folder where `npm install mermaid@11 jsdom@25` was run.");
  process.exit(2);
}
const require = createRequire(path.join(path.resolve(modDir), "noop.js"));
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!DOCTYPE html><body></body>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
const mermaid = (await import(pathToFileURL(path.join(path.resolve(modDir), "node_modules/mermaid/dist/mermaid.core.mjs")).href)).default;
mermaid.initialize({ startOnLoad: false });

const root = process.argv[2] || "docs";
const files = [];
(function walk(d) {
  for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, f.name);
    f.isDirectory() ? walk(p) : p.endsWith(".md") && files.push(p);
  }
})(root);

let n = 0, bad = 0;
for (const f of files) {
  for (const m of fs.readFileSync(f, "utf8").matchAll(/```mermaid\n([\s\S]*?)```/g)) {
    n++;
    try {
      await mermaid.parse(m[1]);
      console.log("OK  ", path.relative(root, f), "|", m[1].split("\n")[0].trim());
    } catch (e) {
      bad++;
      console.log("FAIL", path.relative(root, f), "|", String(e.message || e).split("\n").slice(0, 3).join(" / "));
    }
  }
}
console.log(`diagrams: ${n}, failures: ${bad}`);
process.exit(bad ? 1 : 0);

/**
 * Static preview server for preview.html. Serves the repository root so the
 * page can load fonts/variable/*.ttf and read the cmap with fetch(), which
 * browsers block on file:// URLs. Opens the browser once listening.
 *
 *   bun scripts/serve.ts            # port 8138
 *   PORT=9000 bun scripts/serve.ts  # custom port
 *   OPEN=0 bun scripts/serve.ts     # do not open the browser
 */

import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";
import { spawn } from "node:child_process";

const ROOT = resolve(import.meta.dir, "..");
const PORT = Number(process.env.PORT ?? 8138);
const url = `http://localhost:${PORT}/preview.html`;

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

function openBrowser() {
  if (process.env.OPEN === "0") return;
  spawn("open", [url], { stdio: "ignore", detached: true }).unref();
}

try {
  Bun.serve({
    port: PORT,
    fetch(request) {
      let pathname = decodeURIComponent(new URL(request.url).pathname);
      if (pathname === "/") pathname = "/preview.html";
      const target = normalize(join(ROOT, pathname));
      if (!target.startsWith(ROOT + "/")) return new Response("forbidden", { status: 403 });
      if (!existsSync(target) || !statSync(target).isFile()) return new Response("not found", { status: 404 });
      return new Response(readFileSync(target), {
        headers: {
          "Content-Type": MIME[extname(target)] ?? "application/octet-stream",
          "Cache-Control": "no-cache",
        },
      });
    },
  });
  console.log(`serving ${ROOT} at ${url}`);
  openBrowser();
} catch (error: any) {
  if (error?.code !== "EADDRINUSE") throw error;
  const probe = await fetch(`http://localhost:${PORT}/preview.html`).catch(() => null);
  if (!probe?.ok) {
    console.error(`port ${PORT} is in use by another program; try PORT=9000 make preview`);
    process.exit(1);
  }
  console.log(`port ${PORT} busy — preview already running, opening it`);
  openBrowser();
}

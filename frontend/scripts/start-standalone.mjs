/**
 * Serve the standalone build exactly as the Docker image does: `server.js` with the
 * static assets and public files copied beside it. (`next build` leaves those outside
 * the standalone folder, and `next start` does not serve a standalone build.)
 *
 *   npm start                # http://localhost:3000 (after npm run build)
 *   npm start -- -p 3100     # another port
 */
import { cpSync, existsSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "..");
const standalone = path.join(root, ".next", "standalone");
if (!existsSync(path.join(standalone, "server.js"))) {
  console.error("No standalone build in .next/standalone: run `npm run build` first.");
  process.exit(1);
}
cpSync(path.join(root, ".next", "static"), path.join(standalone, ".next", "static"), { recursive: true });
if (existsSync(path.join(root, "public"))) cpSync(path.join(root, "public"), path.join(standalone, "public"), { recursive: true });

const flag = process.argv.indexOf("-p");
process.env.PORT = flag >= 0 ? process.argv[flag + 1] : (process.env.PORT ?? "3000");
// As in the Docker image. Linux shells export HOSTNAME as the machine's name, which the
// server would otherwise bind to instead of every interface.
process.env.HOSTNAME = "0.0.0.0";
await import(pathToFileURL(path.join(standalone, "server.js")).href);

/**
 * Loads .env.local into process.env for the standalone worker.
 *
 * Next.js does this automatically for the web app, but the worker is a plain
 * Node process and gets nothing. This lives in its own module, imported first,
 * because import bodies are evaluated in order while a bare statement at the top
 * of a module would still run after every import in that module was resolved.
 */
import { existsSync } from "node:fs";

for (const file of [".env.local", ".env"]) {
  if (existsSync(file)) {
    process.loadEnvFile(file);
    break;
  }
}

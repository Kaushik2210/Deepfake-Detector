import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import { serverEnv } from "@/lib/env";
import * as schema from "./schema";

let client: ReturnType<typeof postgres> | null = null;
let database: ReturnType<typeof drizzle<typeof schema>> | null = null;

export function db() {
  if (!database) {
    client = postgres(serverEnv().DATABASE_URL);
    database = drizzle(client, { schema });
  }
  return database;
}

export async function closeDb() {
  await client?.end();
  client = null;
  database = null;
}

export { schema };

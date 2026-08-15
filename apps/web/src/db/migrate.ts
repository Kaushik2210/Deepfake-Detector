import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import postgres from "postgres";

async function main() {
  const url =
    process.env.DATABASE_URL ?? "postgresql://veriframe:veriframe@localhost:5432/veriframe";

  const client = postgres(url, { max: 1 });
  await migrate(drizzle(client), { migrationsFolder: "./drizzle" });
  await client.end();

  console.log("migrations applied");
}

main().catch((error) => {
  console.error("migration failed:", error);
  process.exit(1);
});

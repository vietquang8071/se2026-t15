import { config as loadEnv } from "dotenv";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "prisma/config";

loadEnv({
  path: resolve(dirname(fileURLToPath(import.meta.url)), "../../.env"),
});

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    url:
      process.env.DATABASE_URL ??
      "postgresql://meeting_minutes:meeting_minutes@localhost:5432/meeting_minutes_dev?schema=public",
  },
});

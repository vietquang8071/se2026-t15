import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { defineConfig } from "prisma/config";

config({ path: fileURLToPath(new URL("../../.env", import.meta.url)) });
export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: { path: "prisma/migrations" },
  datasource: {
    url:
      process.env.AUDIO_DATABASE_URL ??
      "postgresql://meeting_minutes:meeting_minutes@localhost:5432/meeting_minutes_audio?schema=public",
  },
});

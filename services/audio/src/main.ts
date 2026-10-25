import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module.js";

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bodyParser: true });
  app.use(
    (
      _request: unknown,
      response: { setHeader: (name: string, value: string) => void },
      next: () => void,
    ) => {
      response.setHeader("Cache-Control", "no-store");
      response.setHeader("X-Content-Type-Options", "nosniff");
      next();
    },
  );
  app.enableShutdownHooks();
  await app.listen(
    Number(process.env.AUDIO_PORT ?? 3002),
    process.env.AUDIO_HOST ?? "127.0.0.1",
  );
}

void bootstrap();

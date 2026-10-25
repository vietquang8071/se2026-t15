import {
  Injectable,
  OnApplicationShutdown,
  OnModuleInit,
} from "@nestjs/common";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "./generated/prisma/client.js";

@Injectable()
export class PrismaService implements OnModuleInit, OnApplicationShutdown {
  readonly client: PrismaClient;

  constructor() {
    const url = process.env.AUDIO_DATABASE_URL;
    if (!url)
      throw new Error(
        "AUDIO_DATABASE_URL is required; audio uses its own database",
      );
    this.client = new PrismaClient({
      adapter: new PrismaPg({ connectionString: url }),
    });
  }

  async onModuleInit() {
    await this.client.$connect();
  }
  async onApplicationShutdown() {
    await this.client.$disconnect();
  }
}

import {
  Controller,
  Get,
  Module,
  ServiceUnavailableException,
} from "@nestjs/common";
import { AudioController, AudioAuthGuard } from "./audio/audio.controller.js";
import { AudioService } from "./audio/audio.service.js";
import { PrismaService } from "./prisma.service.js";

@Controller("health")
class HealthController {
  constructor(private readonly audio: AudioService) {}
  @Get()
  async health() {
    if (!this.audio.available) throw new ServiceUnavailableException();
    try {
      await this.audio.db.$queryRaw`SELECT 1`;
    } catch {
      throw new ServiceUnavailableException();
    }
    return { status: "ok", service: "audio" };
  }
}

@Module({
  controllers: [HealthController, AudioController],
  providers: [PrismaService, AudioService, AudioAuthGuard],
})
export class AppModule {}

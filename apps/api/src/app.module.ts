import { Module } from "@nestjs/common";
import { AppController } from "./app.controller.js";
import { PrismaService } from "./prisma.service.js";

@Module({
  controllers: [AppController],
  providers: [PrismaService],
})
export class AppModule {}

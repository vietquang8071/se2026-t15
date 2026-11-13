import type { Response } from "express";
import { Controller, Get, Header, Headers, Param, Res } from "@nestjs/common";
import {
  ExportService,
  MEETING_REPOSITORY,
  TOKEN_VERIFIER,
  type ScopedMeetingRepository,
  type TokenVerifier,
} from "./export.service.js";

/** Opt-in slice: callers must supply a real trusted verifier before app wiring. */
@Controller("meetings")
export class ExportController {
  constructor(private readonly exports: ExportService) {}

  @Get(":meetingId/export")
  @Header("Cache-Control", "private, no-store")
  @Header("X-Content-Type-Options", "nosniff")
  async download(
    @Headers("authorization") authorization: string | undefined,
    @Param("meetingId") meetingId: string,
    @Res({ passthrough: true }) response: Response,
  ) {
    const result = await this.exports.download(authorization, meetingId);
    response.setHeader(
      "Content-Disposition",
      `attachment; filename="meeting-${meetingId}.json"`,
    );
    return result;
  }
}

export function exportProviders(
  verifier: TokenVerifier,
  repository: ScopedMeetingRepository,
) {
  return [
    ExportService,
    { provide: TOKEN_VERIFIER, useValue: verifier },
    { provide: MEETING_REPOSITORY, useValue: repository },
  ];
}

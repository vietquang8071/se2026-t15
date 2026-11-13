import type { PrismaClient } from "@meeting-minutes/database";
import type { ScopedMeetingRepository } from "./export.service.js";

/** Grants must come from trusted server-side authorization, absent in starter DB. */
export class PrismaMeetingRepository implements ScopedMeetingRepository {
  constructor(private readonly client: PrismaClient) {}

  async findAuthorized(meetingId: string, permittedIds: readonly string[]) {
    return this.client.meeting.findFirst({
      where: { AND: [{ id: meetingId }, { id: { in: [...permittedIds] } }] },
      select: { id: true, title: true, anchorDate: true },
    });
  }
}

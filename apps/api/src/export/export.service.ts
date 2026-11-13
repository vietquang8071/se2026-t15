import {
  BadRequestException,
  Inject,
  Injectable,
  NotFoundException,
  ServiceUnavailableException,
  UnauthorizedException,
} from "@nestjs/common";

export interface Principal {
  readonly id: string;
  /** Server-owned grants from a trusted verifier, never request parameters. */
  readonly meetingIds: readonly string[];
}
export interface TokenVerifier {
  verify(token: string): Promise<Principal | null>;
}
export interface ScopedMeetingRepository {
  findAuthorized(
    meetingId: string,
    permittedIds: readonly string[],
  ): Promise<unknown>;
}
export const TOKEN_VERIFIER = Symbol("TOKEN_VERIFIER");
export const MEETING_REPOSITORY = Symbol("MEETING_REPOSITORY");

@Injectable()
export class ExportService {
  constructor(
    @Inject(TOKEN_VERIFIER) private readonly verifier: TokenVerifier,
    @Inject(MEETING_REPOSITORY)
    private readonly repository: ScopedMeetingRepository,
  ) {}

  async download(authorization: string | undefined, meetingId: string) {
    const token = /^Bearer ([^\s]+)$/.exec(authorization ?? "")?.[1];
    if (!token) throw new UnauthorizedException();
    let principal: Principal | null;
    try {
      principal = await this.verifier.verify(token);
    } catch {
      throw new ServiceUnavailableException();
    }
    if (
      !principal ||
      typeof principal.id !== "string" ||
      !principal.id ||
      !Array.isArray(principal.meetingIds) ||
      !principal.meetingIds.every((id) => typeof id === "string")
    ) {
      throw new UnauthorizedException();
    }
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(meetingId))
      throw new BadRequestException();
    // Snapshot grants before awaiting persistence; no shared request state.
    const grants = [...principal.meetingIds];
    if (!grants.includes(meetingId)) throw new NotFoundException();
    let row: unknown;
    try {
      row = await this.repository.findAuthorized(meetingId, grants);
    } catch {
      throw new ServiceUnavailableException();
    }
    if (row === null) throw new NotFoundException();
    if (
      typeof row !== "object" ||
      row === null ||
      !("id" in row) ||
      row.id !== meetingId ||
      !("title" in row) ||
      typeof row.title !== "string" ||
      !("anchorDate" in row) ||
      !(row.anchorDate instanceof Date) ||
      !Number.isFinite(row.anchorDate.getTime())
    ) {
      throw new ServiceUnavailableException();
    }
    return {
      id: meetingId,
      title: row.title,
      anchor_date: row.anchorDate.toISOString().slice(0, 10),
    };
  }
}

// Kịch bản AD-060; không thuộc source chính thức.
export type Segment = { id: string; start: number; end: number; speaker_id: string | null; text: string };
export type TranscriptInput = { contract_version: '1.0'; source_id: string; external_id: string; segments: Segment[] };
export type Result = { status: number; body: Record<string, unknown> };
export interface TranscriptRepository {
  ownerOf(meetingId: string): Promise<string | null>;
  save(meetingId: string, actor: string, input: TranscriptInput): Promise<Result>;
}
export class InputError extends Error {}

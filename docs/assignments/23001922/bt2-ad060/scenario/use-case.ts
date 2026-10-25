import type { Result, TranscriptInput, TranscriptRepository } from './contracts.ts';

// Đích dự kiến: apps/api/src/transcripts/import-transcript.ts.
// Use case chỉ nhận contract nội bộ, không import SDK/DTO của vendor.
export async function importTranscript(
  input: TranscriptInput, meetingId: string, actor: string, repository: TranscriptRepository,
): Promise<Result> {
  const owner = await repository.ownerOf(meetingId);
  if (owner === null) return { status: 404, body: { code: 'MEETING_NOT_FOUND' } };
  if (owner !== actor) return { status: 403, body: { code: 'FORBIDDEN' } };
  return repository.save(meetingId, actor, input);
}

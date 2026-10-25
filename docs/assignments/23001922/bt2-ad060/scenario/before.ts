import { InputError } from './contracts.ts';
import type { Result, TranscriptInput, TranscriptRepository } from './contracts.ts';

// Đích dự kiến: apps/api/src/transcripts/import-transcript.ts (MVP minh họa).
export async function importTranscriptBefore(
  payload: any, meetingId: string, actor: string, repository: TranscriptRepository,
): Promise<Result> {
  try {
    // Validation và hiểu định dạng vendor cùng nằm trong hàm điều phối.
    if (!payload || payload.format !== 'v1' || typeof payload.document !== 'string' ||
        !payload.document.trim() || typeof payload.revision !== 'string' ||
        !payload.revision.trim() || !Array.isArray(payload.utterances) ||
        payload.utterances.length === 0 || payload.utterances.length > 1000) {
      throw new InputError('BAD_VENDOR_PAYLOAD');
    }
    const segments = payload.utterances.map((item: any, index: number) => {
      if (!item || !Number.isFinite(item.from_ms) || !Number.isFinite(item.to_ms) ||
          item.from_ms < 0 || item.to_ms <= item.from_ms ||
          typeof item.content !== 'string' || !item.content.trim() ||
          !(item.person === null || typeof item.person === 'string')) {
        throw new InputError('BAD_VENDOR_PAYLOAD');
      }
      return { id: `seg-${index + 1}`, start: item.from_ms / 1000,
        end: item.to_ms / 1000, speaker_id: item.person, text: item.content };
    });
    const input: TranscriptInput = { contract_version: '1.0', source_id: 'vtranscript',
      external_id: JSON.stringify([payload.document, payload.revision]), segments };
    // Business rule: chỉ chủ cuộc họp được nhập transcript.
    const owner = await repository.ownerOf(meetingId);
    if (owner === null) return { status: 404, body: { code: 'MEETING_NOT_FOUND' } };
    if (owner !== actor) return { status: 403, body: { code: 'FORBIDDEN' } };
    // Persistence: transaction chống trùng và kiểm lại quyền tại DB.
    const result = await repository.save(meetingId, actor, input);
    return result;
  } catch (error) {
    if (error instanceof InputError) return { status: 400, body: { code: error.message } };
    return { status: 503, body: { code: 'STORE_UNAVAILABLE' } };
  }
}

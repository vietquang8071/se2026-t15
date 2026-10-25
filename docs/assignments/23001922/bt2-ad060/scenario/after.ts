import { InputError } from './contracts.ts';
import type { Result, TranscriptRepository } from './contracts.ts';
import { mapVendorPayload } from './adapter.ts';

import { importTranscript } from './use-case.ts';

// Facade characterization: giữ input/output cũ trước khi di chuyển deployment.
export async function importTranscriptAfter(
  payload: any, meetingId: string, actor: string, repository: TranscriptRepository,
): Promise<Result> {
  try {
    const input = mapVendorPayload(payload);
    return await importTranscript(input, meetingId, actor, repository);
  } catch (error) {
    if (error instanceof InputError) return { status: 400, body: { code: error.message } };
    return { status: 503, body: { code: 'STORE_UNAVAILABLE' } };
  }
}

import { InputError } from './contracts.ts';
import type { TranscriptInput } from './contracts.ts';

// Đích cuối dự kiến: apps/transcript-gateway/src/vtranscript-adapter.ts.
// Extract nguyên validation/mapping của before; không đổi thứ tự hoặc nội dung text.
export function mapVendorPayload(payload: any): TranscriptInput {
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
  return { contract_version: '1.0', source_id: 'vtranscript',
    external_id: JSON.stringify([payload.document, payload.revision]), segments };
}

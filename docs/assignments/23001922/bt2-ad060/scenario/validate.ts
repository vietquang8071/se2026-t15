import { InputError } from './contracts.ts';
import type { TranscriptInput } from './contracts.ts';
// Bổ sung boundary HTTP cho thiết kế cuối: thay đổi riêng sau refactoring.
export function validateInternal(input: any): asserts input is TranscriptInput {
  if (!input || input.contract_version !== '1.0' ||
      typeof input.source_id !== 'string' || !input.source_id.trim() ||
      typeof input.external_id !== 'string' || !input.external_id.trim() ||
      !Array.isArray(input.segments) || input.segments.length === 0 ||
      input.segments.length > 1000) throw new InputError('BAD_INTERNAL_PAYLOAD');
  const ids = new Set();
  for (const segment of input.segments) {
    if (!segment || typeof segment.id !== 'string' || !segment.id.trim() ||
        ids.has(segment.id) || !Number.isFinite(segment.start) ||
        !Number.isFinite(segment.end) || segment.start < 0 || segment.end <= segment.start ||
        typeof segment.text !== 'string' || !segment.text.trim() ||
        !(segment.speaker_id === null || typeof segment.speaker_id === 'string')) {
      throw new InputError('BAD_INTERNAL_PAYLOAD');
    }
    ids.add(segment.id);
  }
}

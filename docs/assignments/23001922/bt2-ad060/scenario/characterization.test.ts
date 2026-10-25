import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { importTranscriptBefore } from './before.ts';
import { importTranscriptAfter } from './after.ts';
import { mapVendorPayload } from './adapter.ts';
import { DAYS_70, retainOperational } from './retention.ts';
const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url), 'utf8'));
function fakeRepository(owner: string | null = 'son', fail = false) {
  const rows = new Map();
  const calls: string[] = [];
  return { rows, calls,
    async ownerOf() { calls.push('owner'); return owner; },
    async save(meetingId: string, actor: string, input: any) {
      calls.push('save');
      if (fail) throw new Error('connection lost');
      const key = JSON.stringify([meetingId, input.source_id, input.external_id]);
      const old = rows.get(key);
      const data = JSON.stringify(input.segments);
      if (old && old !== data) return { status: 409, body: { code: 'IDEMPOTENCY_CONFLICT' } };
      if (old) return { status: 200, body: { code: 'ALREADY_IMPORTED' } };
      rows.set(key, data);
      return { status: 201, body: { code: 'IMPORTED' } };
    },
  };
}
const cases = [
  { name: 'success', payload: fixture, owner: 'son', actor: 'son', expected: 201 },
  { name: 'bad payload before authorization', payload: {}, owner: 'other', actor: 'son', expected: 400 },
  { name: 'bad timestamp', payload: { ...fixture, utterances: [{ ...fixture.utterances[0], to_ms: 1 }] }, owner: 'son', actor: 'son', expected: 400 },
  { name: 'empty text', payload: { ...fixture, utterances: [{ ...fixture.utterances[0], content: '  ' }] }, owner: 'son', actor: 'son', expected: 400 },
  { name: 'missing meeting', payload: fixture, owner: null, actor: 'son', expected: 404 },
  { name: 'forbidden', payload: fixture, owner: 'other', actor: 'son', expected: 403 },
  { name: 'database failure', payload: fixture, owner: 'son', actor: 'son', fail: true, expected: 503 },
];
for (const item of cases) {
  test(`characterization: ${item.name}`, async () => {
    const a = fakeRepository(item.owner, item.fail);
    const b = fakeRepository(item.owner, item.fail);
    const before = await importTranscriptBefore(item.payload, 'm1', item.actor, a);
    const after = await importTranscriptAfter(item.payload, 'm1', item.actor, b);
    assert.equal(before.status, item.expected);
    assert.deepEqual(after, before);
    assert.deepEqual([...b.rows], [...a.rows]);
    assert.deepEqual(b.calls, a.calls);
  });
}
test('characterization: retry and changed body conflict', async () => {
  const outputs = [];
  for (const fn of [importTranscriptBefore, importTranscriptAfter]) {
    const repo = fakeRepository();
    const changed = structuredClone(fixture);
    changed.utterances[0].content = 'Nội dung mới';
    const result = [await fn(fixture, 'm1', 'son', repo), await fn(fixture, 'm1', 'son', repo),
      await fn(changed, 'm1', 'son', repo)];
    assert.deepEqual(result.map(x => x.status), [201, 200, 409]);
    outputs.push({ result, rows: [...repo.rows], calls: repo.calls });
  }
  assert.deepEqual(outputs[0], outputs[1]);
});
test('adapter: milliseconds to seconds, keep text and speaker', () => {
  const mapped = mapVendorPayload(fixture);
  assert.deepEqual(mapped.segments, [{ id: 'seg-1', start: 12.5, end: 18.2,
    speaker_id: 'speaker_1', text: fixture.utterances[0].content }]);
});
test('adapter: null speaker, bad version and excessive segments', () => {
  const data = structuredClone(fixture);
  data.utterances[0].person = null;
  assert.equal(mapVendorPayload(data).segments[0].speaker_id, null);
  assert.throws(() => mapVendorPayload({ ...fixture, format: 'v2' }));
  assert.throws(() => mapVendorPayload({ ...fixture, utterances: Array(1001).fill(fixture.utterances[0]) }));
});
test('retention: exact 70 day boundary applies also to pending references', () => {
  const now = Date.UTC(2026, 9, 25);
  const rows = [
    { createdAt: now - DAYS_70 + 1, state: 'PENDING', remoteReference: 'keep' },
    { createdAt: now - DAYS_70, state: 'PENDING', remoteReference: 'delete' },
    { createdAt: now - DAYS_70 - 1, state: 'IMPORTED', remoteReference: null },
  ];
  assert.deepEqual(retainOperational(rows, now), [rows[0]]);
  assert.equal(rows.length, 3);
});

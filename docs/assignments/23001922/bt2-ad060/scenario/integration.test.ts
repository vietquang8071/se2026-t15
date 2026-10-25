import test, { after, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pgRepository } from './pg-repository.ts';
import { makeServer } from './server.ts';
import { mapVendorPayload } from './adapter.ts';
const container = process.env.AD060_PG_CONTAINER;
if (!container) throw new Error('Set AD060_PG_CONTAINER to the isolated test container');
const repository = pgRepository(container);
const input = mapVendorPayload(JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url), 'utf8')));
let failGateway = false;
const server = makeServer(repository, async () => {
  if (failGateway) return new Promise(() => {});
  return input;
});
let url: string;
before(async () => {
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (typeof address === 'object' && address) url = `http://127.0.0.1:${address.port}`;
});
after(async () => { await new Promise<void>(resolve => server.close(() => resolve())); });
async function post(body: unknown, user = 'son') {
  return fetch(url + '/meetings/m1/transcripts', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-test-user': user }, body: JSON.stringify(body) });
}
test('direct HTTP: unauthorized actor cannot import through bypassed UI', async () => {
  const response = await post(input, 'other');
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { code: 'FORBIDDEN' });
});
test('direct HTTP: invalid canonical payload is rejected', async () => {
  const response = await post({ ...input, segments: [{ ...input.segments[0], end: -1 }] });
  assert.equal(response.status, 400);
});
test('PostgreSQL: concurrent HTTP duplicates produce exactly one stored revision', async () => {
  const responses = await Promise.all([post(input), post(input)]);
  assert.deepEqual(responses.map(r => r.status).sort(), [200, 201]);
});
test('PostgreSQL: same key with changed data returns conflict; original survives', async () => {
  const changed = structuredClone(input);
  changed.segments[0].text = 'Không được ghi đè';
  assert.equal((await post(changed)).status, 409);
  assert.equal((await post(input)).status, 200);
});
test('PostgreSQL boundary: save itself rejects a forged actor', async () => {
  const result = await repository.save('m1', 'other', { ...input, external_id: 'forged' });
  assert.equal(result.status, 403);
});
test('fault injection: gateway timeout leaves PENDING and core reads still return minutes', async () => {
  failGateway = true;
  const [pending, core] = await Promise.all([
    fetch(url + '/meetings/m1/imports/fetch', { method: 'POST', headers: { 'x-test-user': 'son' } }),
    fetch(url + '/meetings/m1/minutes', { headers: { 'x-test-user': 'son' } }),
  ]);
  assert.equal(pending.status, 202);
  assert.equal((await pending.json()).state, 'PENDING');
  assert.equal(core.status, 200);
  assert.equal((await core.json()).summary, 'Biên bản đã lưu');
  const state = await fetch(url + '/imports/job-1', { headers: { 'x-test-user': 'son' } });
  assert.equal((await state.json()).state, 'PENDING');
  failGateway = false;
  const retry = await fetch(url + '/meetings/m1/imports/fetch', { method: 'POST', headers: { 'x-test-user': 'son' } });
  assert.equal(retry.status, 200); // existing content, no duplicate
});

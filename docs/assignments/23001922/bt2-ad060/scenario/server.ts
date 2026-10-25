import { createServer } from 'node:http';
import { InputError } from './contracts.ts';
import type { TranscriptRepository } from './contracts.ts';
import { importTranscript } from './use-case.ts';
import { validateInternal } from './validate.ts';

// HTTP harness local; không phải NestJS app hoặc authentication production.
export function makeServer(repository: TranscriptRepository, getNormalized: () => Promise<unknown>) {
  const jobs = new Map<string, string>(); // Chỉ fake lifecycle; production phải persist qua API repository.
  return createServer(async (request, response) => {
    let result;
    try {
      const actor = String(request.headers['x-test-user'] ?? '');
      if (request.method === 'GET' && request.url === '/meetings/m1/minutes') {
        if (await repository.ownerOf('m1') !== actor) result = { status: 403, body: { code: 'FORBIDDEN' } };
        else result = { status: 200, body: { summary: 'Biên bản đã lưu', source: 'seed-fixture' } };
      } else if (request.method === 'POST' && request.url === '/meetings/m1/imports/fetch') {
        if (await repository.ownerOf('m1') !== actor) result = { status: 403, body: { code: 'FORBIDDEN' } };
        else {
          jobs.set('job-1', 'PENDING');
          let timer: ReturnType<typeof setTimeout> | undefined;
          try {
            const input = await Promise.race([getNormalized(), new Promise((_, reject) => {
              timer = setTimeout(() => reject(new Error('GATEWAY_TIMEOUT')), 50);
            })]);
            validateInternal(input);
            result = await importTranscript(input, 'm1', actor, repository);
            jobs.set('job-1', result.status < 300 ? 'IMPORTED' : 'FAILED');
          } catch (error) {
            if (error instanceof InputError) {
              jobs.set('job-1', 'FAILED');
              result = { status: 400, body: { code: error.message } };
            } else result = { status: 202, body: { job_id: 'job-1', state: 'PENDING', code: 'GATEWAY_UNAVAILABLE' } };
          } finally { clearTimeout(timer); }
        }
      } else if (request.method === 'GET' && request.url === '/imports/job-1') {
        if (await repository.ownerOf('m1') !== actor) result = { status: 403, body: { code: 'FORBIDDEN' } };
        else result = { status: 200, body: { state: jobs.get('job-1') } };
      } else if (request.method === 'POST' && request.url === '/meetings/m1/transcripts') {
        let body = '';
        for await (const chunk of request) {
          body += chunk;
          if (Buffer.byteLength(body) > 1024 * 1024) throw new InputError('BODY_TOO_LARGE');
        }
        let input;
        try { input = JSON.parse(body); } catch { throw new InputError('BAD_JSON'); }
        validateInternal(input);
        result = await importTranscript(input, 'm1', actor, repository);
      } else result = { status: 404, body: { code: 'NOT_FOUND' } };
    } catch (error) {
      result = error instanceof InputError
        ? { status: error.message === 'BODY_TOO_LARGE' ? 413 : 400, body: { code: error.message } }
        : { status: 503, body: { code: 'STORE_UNAVAILABLE' } };
    }
    response.writeHead(result.status, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify(result.body));
  });
}

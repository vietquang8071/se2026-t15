import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import type { TranscriptInput, TranscriptRepository } from './contracts.ts';
const run = promisify(execFile);
const quote = (value: string) => "'" + value.replaceAll("'", "''") + "'";
export function pgRepository(container: string): TranscriptRepository {
  // Test bridge qua psql; implementation sản phẩm sẽ dùng Prisma + parameters.
  async function sql(statement: string) {
    const { stdout } = await run('docker', ['exec', '-i', container, 'psql', '-X', '-qAt',
      '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'ad060', '-c', statement]);
    return stdout.trim();
  }
  return {
    async ownerOf(meetingId) {
      return await sql(`SELECT owner_id FROM ad060.meetings WHERE id=${quote(meetingId)}`) || null;
    },
    async save(meetingId: string, actor: string, input: TranscriptInput) {
      return JSON.parse(await sql(`SELECT ad060.store_revision(${quote(meetingId)},${quote(actor)},` +
        `${quote(input.source_id)},${quote(input.external_id)},${quote(JSON.stringify(input.segments))}::jsonb)`));
    },
  };
}

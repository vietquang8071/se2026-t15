export type OperationalRecord = { createdAt: number; state: string; remoteReference: string | null };
export const DAYS_70 = 70 * 24 * 60 * 60 * 1000;
// Mô phỏng trên bản sao: không xóa dữ liệu thật.
export function retainOperational(records: OperationalRecord[], now: number) {
  return records.filter(record => now - record.createdAt < DAYS_70);
}

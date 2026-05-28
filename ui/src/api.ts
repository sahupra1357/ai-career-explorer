import type { FieldSummary, CompareSuccess, CompareError } from './types';

const BASE = '';

export async function fetchFields(): Promise<FieldSummary[]> {
  const res = await fetch(`${BASE}/api/fields`);
  if (!res.ok) throw new Error('Failed to load fields');
  return res.json();
}

export type CompareResult =
  | { ok: true; data: CompareSuccess }
  | { ok: false; status: number; error: CompareError }
  | { ok: false; status: 0; error: null; message: string };

export async function compareFields(fieldIds: string[]): Promise<CompareResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields: fieldIds }),
    });
  } catch {
    return { ok: false, status: 0, error: null, message: 'Could not reach the server. Is the backend running?' };
  }

  if (res.ok) {
    return { ok: true, data: await res.json() };
  }

  return { ok: false, status: res.status, error: await res.json() };
}

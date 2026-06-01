import type { FieldSummary, CompareSuccess, CompareError, ExploreResponse, DirectResponse } from './types';

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

export type ExploreResult =
  | { ok: true; data: ExploreResponse }
  | { ok: false; message: string; newSessionId?: string };

export async function sendExploreMessage(
  message: string,
  sessionId: string | null,
): Promise<ExploreResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/explore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  } catch {
    return { ok: false, message: 'Could not reach the server. Is the backend running?' };
  }

  if (res.status === 404) {
    const body = await res.json();
    return { ok: false, message: 'Session expired — starting fresh.', newSessionId: body.session_id };
  }

  if (res.status === 503) {
    const body = await res.json();
    return { ok: false, message: body.message ?? 'Service temporarily unavailable.' };
  }

  if (res.ok) {
    return { ok: true, data: await res.json() };
  }

  return { ok: false, message: 'Something went wrong. Please try again.' };
}

export type DirectResult =
  | { ok: true; data: DirectResponse }
  | { ok: false; message: string };

export async function fetchDeepDive(fieldId: string): Promise<DirectResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/direct`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field_id: fieldId }),
    });
  } catch {
    return { ok: false, message: 'Could not reach the server. Is the backend running?' };
  }

  if (res.ok) {
    return { ok: true, data: await res.json() };
  }

  const body = await res.json().catch(() => ({}));
  return { ok: false, message: body.message ?? 'Field not found.' };
}

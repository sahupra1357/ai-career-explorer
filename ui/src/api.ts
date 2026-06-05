import type {
  FieldSummary,
  CompareSuccess,
  CompareError,
  ExploreResponse,
  DirectResponse,
  CourseSearchResponse,
} from './types';

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

export type CourseSearchResult =
  | { ok: true; data: CourseSearchResponse }
  | { ok: false; message: string };

export interface CourseSearchPayload {
  course_query: string;
  city?: string;
  state?: string;
  home_state?: string;
}

export async function searchCourses(payload: CourseSearchPayload): Promise<CourseSearchResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/course-search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, message: 'Could not reach the server. Is the backend running?' };
  }

  if (res.ok) {
    return { ok: true, data: await res.json() };
  }

  const body = await res.json().catch(() => ({}));
  return { ok: false, message: body.message ?? 'Course search failed. Please check the course and location.' };
}

export interface SearchProgress {
  phase: 'starting' | 'seeded' | 'investigating';
  done?: number;
  total?: number;
}

// Streaming variant: reports live progress (colleges investigated) via onProgress,
// then resolves with the final result. Falls back gracefully on any stream error.
export async function searchCoursesStream(
  payload: CourseSearchPayload,
  onProgress: (p: SearchProgress) => void,
): Promise<CourseSearchResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/course-search/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, message: 'Could not reach the server. Is the backend running?' };
  }
  if (!res.ok || !res.body) {
    return { ok: false, message: 'Course search failed. Please check the course and location.' };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: CourseSearchResponse | null = null;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() ?? '';
      for (const chunk of chunks) {
        const line = chunk.split('\n').find((l) => l.startsWith('data:'));
        if (!line) continue;
        let event: { phase: string; message?: string; result?: CourseSearchResponse; done?: number; total?: number };
        try {
          event = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (event.phase === 'done') final = event.result ?? null;
        else if (event.phase === 'error') return { ok: false, message: event.message ?? 'Search failed.' };
        else onProgress(event as SearchProgress);
      }
    }
  } catch {
    return { ok: false, message: 'Connection interrupted during search. Please try again.' };
  }

  if (final) return { ok: true, data: final };
  return { ok: false, message: 'Search ended without a result.' };
}

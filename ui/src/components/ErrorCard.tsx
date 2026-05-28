import type { CompareError } from '../types';

interface Props {
  status: number;
  error: CompareError | null;
  message?: string;
}

export default function ErrorCard({ status, error, message }: Props) {
  if (!error && message) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        <p className="font-semibold mb-1">Connection error</p>
        <p>{message}</p>
      </div>
    );
  }

  if (!error) return null;

  if (error.error === 'not_found') {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm">
        <p className="font-semibold text-amber-800 mb-1">Field not found</p>
        <p className="text-amber-700">{error.message}</p>
        {error.suggestions.length > 0 && (
          <div className="mt-3">
            <p className="text-amber-600 text-xs font-medium mb-1">Did you mean:</p>
            <ul className="list-disc list-inside text-amber-700 space-y-0.5">
              {error.suggestions.map((s) => <li key={s}><code className="text-xs bg-amber-100 px-1 rounded">{s}</code></li>)}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (error.error === 'partial_not_found') {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm">
        <p className="font-semibold text-amber-800 mb-2">Some fields not found</p>
        <p className="text-amber-700 mb-1">
          <span className="font-medium">Found:</span> {error.found.join(', ')}
        </p>
        <p className="text-amber-700 mb-2">
          <span className="font-medium">Not found:</span> {error.not_found.join(', ')}
        </p>
        {Object.entries(error.suggestions).map(([fid, suggs]) =>
          suggs.length > 0 ? (
            <div key={fid} className="mt-2">
              <p className="text-amber-600 text-xs font-medium mb-1">Suggestions for "{fid}":</p>
              <ul className="list-disc list-inside text-amber-700 space-y-0.5">
                {suggs.map((s) => <li key={s}><code className="text-xs bg-amber-100 px-1 rounded">{s}</code></li>)}
              </ul>
            </div>
          ) : null
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
      <p className="font-semibold">Unexpected error (HTTP {status})</p>
    </div>
  );
}

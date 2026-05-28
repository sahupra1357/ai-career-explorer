import { useState, useEffect } from 'react';
import { fetchFields, compareFields } from './api';
import type { FieldSummary, CompareSuccess, CompareError } from './types';
import FieldAutocomplete from './components/FieldAutocomplete';
import ComparisonResult from './components/ComparisonResult';
import ErrorCard from './components/ErrorCard';

type AppState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'success'; data: CompareSuccess }
  | { phase: 'error'; status: number; error: CompareError | null; message?: string };

export default function App() {
  const [knownFields, setKnownFields] = useState<FieldSummary[]>([]);
  const [selections, setSelections] = useState<[string, string, string]>(['', '', '']);
  const [state, setState] = useState<AppState>({ phase: 'idle' });

  useEffect(() => {
    fetchFields().then(setKnownFields).catch(() => {});
  }, []);

  function setSelection(index: number, value: string) {
    setSelections((prev) => {
      const next = [...prev] as [string, string, string];
      next[index] = value;
      return next;
    });
  }

  function clearSelection(index: number) {
    setSelection(index, '');
    setState({ phase: 'idle' });
  }

  const chosen = selections.filter(Boolean);
  const canCompare = chosen.length >= 2;

  async function handleCompare() {
    if (!canCompare) return;
    setState({ phase: 'loading' });
    const result = await compareFields(chosen);
    if (result.ok) {
      setState({ phase: 'success', data: result.data });
    } else if ('message' in result) {
      setState({ phase: 'error', status: 0, error: null, message: result.message });
    } else {
      setState({ phase: 'error', status: result.status, error: result.error });
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* Header */}
        <header className="text-center mb-10">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">STEM Career Explorer</h1>
          <p className="mt-2 text-slate-500 text-base">
            Compare STEM fields side by side — built for high school students choosing a direction.
          </p>
        </header>

        {/* Field selector */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <p className="text-sm font-medium text-slate-600 mb-4">Choose 2 or 3 STEM fields to compare:</p>

          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            {[0, 1, 2].map((i) => (
              <FieldAutocomplete
                key={i}
                index={i}
                value={selections[i]}
                fields={knownFields}
                selected={selections.filter(Boolean)}
                onChange={(v) => { setSelection(i, v); setState({ phase: 'idle' }); }}
                onClear={() => clearSelection(i)}
              />
            ))}
          </div>

          <button
            onClick={handleCompare}
            disabled={!canCompare || state.phase === 'loading'}
            className={`w-full sm:w-auto px-6 py-2.5 rounded-lg text-sm font-semibold transition-all ${
              canCompare && state.phase !== 'loading'
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            {state.phase === 'loading' ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Comparing…
              </span>
            ) : 'Compare fields'}
          </button>
        </div>

        {/* Results */}
        {state.phase === 'error' && (
          <div className="mt-6">
            <ErrorCard status={state.status} error={state.error} message={state.message} />
          </div>
        )}

        {state.phase === 'success' && (
          <ComparisonResult result={state.data} />
        )}

        {/* Footer */}
        <footer className="mt-16 text-center text-xs text-slate-400">
          Salary data: BLS Occupational Outlook Handbook · AI summaries via Claude
        </footer>
      </div>
    </div>
  );
}

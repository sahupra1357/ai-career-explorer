import { useState, useEffect } from 'react';
import { fetchFields, compareFields } from './api';
import type { FieldSummary, CompareSuccess, CompareError } from './types';
import FieldAutocomplete from './components/FieldAutocomplete';
import ComparisonResult from './components/ComparisonResult';
import ErrorCard from './components/ErrorCard';
import ChatInterface from './components/ChatInterface';
import DeepDivePage from './components/DeepDivePage';
import CourseFinder from './components/CourseFinder';

type Tab = 'course' | 'compare' | 'explore' | 'deepdive';

type CompareState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'success'; data: CompareSuccess }
  | { phase: 'error'; status: number; error: CompareError | null; message?: string };

export default function App() {
  const [tab, setTab] = useState<Tab>('course');
  const [deepDiveFieldId, setDeepDiveFieldId] = useState<string | null>(null);

  // Compare tab state
  const [knownFields, setKnownFields] = useState<FieldSummary[]>([]);
  const [selections, setSelections] = useState<[string, string, string]>(['', '', '']);
  const [compareState, setCompareState] = useState<CompareState>({ phase: 'idle' });

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
    setCompareState({ phase: 'idle' });
  }

  const chosen = selections.filter(Boolean);
  const canCompare = chosen.length >= 2;

  async function handleCompare() {
    if (!canCompare) return;
    setCompareState({ phase: 'loading' });
    const result = await compareFields(chosen);
    if (result.ok) {
      setCompareState({ phase: 'success', data: result.data });
    } else if ('message' in result) {
      setCompareState({ phase: 'error', status: 0, error: null, message: result.message });
    } else {
      setCompareState({ phase: 'error', status: result.status, error: result.error });
    }
  }

  function handleDeepDive(fieldId: string) {
    setDeepDiveFieldId(fieldId);
    setTab('deepdive');
  }

  function handleBackFromDeepDive() {
    setTab('explore');
    setDeepDiveFieldId(null);
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'course', label: 'Course Finder' },
    { id: 'compare', label: 'Compare' },
    { id: 'explore', label: 'Explore' },
    { id: 'deepdive', label: 'Deep Dive' },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* Header */}
        <header className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">STEM Career Explorer</h1>
          <p className="mt-2 text-slate-500 text-base">
            Compare paths, inspect college programs, and shortlist evidence-backed options.
          </p>
        </header>

        {/* Tab nav */}
        <div className="flex gap-1 bg-white rounded-xl border border-slate-200 p-1 mb-6 w-fit mx-auto shadow-sm">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Course Finder tab */}
        {tab === 'course' && <CourseFinder />}

        {/* Compare tab */}
        {tab === 'compare' && (
          <>
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
                    onChange={(v) => { setSelection(i, v); setCompareState({ phase: 'idle' }); }}
                    onClear={() => clearSelection(i)}
                  />
                ))}
              </div>

              <button
                onClick={handleCompare}
                disabled={!canCompare || compareState.phase === 'loading'}
                className={`w-full sm:w-auto px-6 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  canCompare && compareState.phase !== 'loading'
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm'
                    : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                }`}
              >
                {compareState.phase === 'loading' ? (
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

            {compareState.phase === 'error' && (
              <div className="mt-6">
                <ErrorCard status={compareState.status} error={compareState.error} message={compareState.message} />
              </div>
            )}

            {compareState.phase === 'success' && (
              <ComparisonResult result={compareState.data} />
            )}
          </>
        )}

        {/* Explore tab */}
        {tab === 'explore' && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <p className="text-sm font-medium text-slate-600 mb-4">
              Tell me about yourself and I'll match you with STEM fields:
            </p>
            <ChatInterface onDeepDive={handleDeepDive} />
          </div>
        )}

        {/* Deep Dive tab */}
        {tab === 'deepdive' && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            {deepDiveFieldId ? (
              <DeepDivePage fieldId={deepDiveFieldId} onBack={handleBackFromDeepDive} />
            ) : (
              <div className="text-center py-12 text-slate-400">
                <p className="text-sm">
                  Use the <strong className="text-slate-600">Explore</strong> tab to find fields, then click{' '}
                  <strong className="text-slate-600">Deep dive →</strong> on any recommendation.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <footer className="mt-16 text-center text-xs text-slate-400">
          Salary data: BLS Occupational Outlook Handbook · AI summaries via Claude
        </footer>
      </div>
    </div>
  );
}

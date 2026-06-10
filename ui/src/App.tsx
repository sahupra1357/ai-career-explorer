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
  const [mounted, setMounted] = useState<Set<Tab>>(() => new Set<Tab>(['course']));
  const [dark, setDark] = useState<boolean>(() => {
    try { return localStorage.getItem('theme') === 'dark'; } catch { return false; }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch { /* ignore */ }
  }, [dark]);

  useEffect(() => {
    setMounted((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)));
  }, [tab]);

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
    { id: 'course',   label: 'Course Finder' },
    { id: 'compare',  label: 'Compare' },
    { id: 'explore',  label: 'Explore' },
    { id: 'deepdive', label: 'Deep Dive' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>

      {/* Amber top accent line */}
      <div style={{ height: 3, background: 'var(--top-stripe)' }} />

      {/* Header */}
      <header style={{ background: 'var(--s1)', borderBottom: '1px solid var(--bdr)' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', padding: '0 24px' }}>
          {/* Brand row */}
          <div style={{ padding: '20px 0 16px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <h1 style={{
              margin: 0,
              fontFamily: 'var(--fd)',
              fontSize: 22,
              fontWeight: 700,
              color: 'var(--t1)',
              letterSpacing: '-0.02em',
            }}>
              STEM Career Explorer
            </h1>
            <span style={{
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--t3)',
              flex: 1,
            }}>
              Evidence-backed program research
            </span>
            <button
              className="xtheme"
              onClick={() => setDark((d) => !d)}
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {dark ? (
                /* Sun icon */
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <circle cx="10" cy="10" r="3.5" />
                  <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42" />
                </svg>
              ) : (
                /* Moon icon */
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <path d="M17.5 11.5A7.5 7.5 0 0 1 8.5 2.5a7.5 7.5 0 1 0 9 9z" />
                </svg>
              )}
            </button>
          </div>

          {/* Tab nav */}
          <nav style={{ display: 'flex', gap: 2 }}>
            {tabs.map(({ id, label }) => {
              const active = tab === id;
              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  style={{
                    padding: '9px 18px',
                    background: 'none',
                    border: 'none',
                    borderBottom: active ? '2px solid var(--amber)' : '2px solid transparent',
                    color: active ? 'var(--amber-lt)' : 'var(--t2)',
                    fontFamily: 'var(--fb)',
                    fontSize: 13,
                    fontWeight: active ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'color 0.12s, border-color 0.12s',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--t1)'; }}
                  onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--t2)'; }}
                >
                  {label}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px 80px' }}>

        {/* Course Finder */}
        {mounted.has('course') && (
          <div className={tab === 'course' ? '' : 'hidden'}>
            <CourseFinder />
          </div>
        )}

        {/* Compare */}
        {mounted.has('compare') && (
          <div className={tab === 'compare' ? '' : 'hidden'}>
            <div className="xc" style={{ padding: 24 }}>
              <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--t2)' }}>
                Choose 2 or 3 STEM fields to compare:
              </p>
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
                className="xbtn"
              >
                {compareState.phase === 'loading' ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Comparing…
                  </>
                ) : 'Compare fields'}
              </button>
            </div>

            {compareState.phase === 'error' && (
              <div className="mt-6">
                <ErrorCard status={compareState.status} error={compareState.error} message={compareState.message} />
              </div>
            )}
            {compareState.phase === 'success' && <ComparisonResult result={compareState.data} />}
          </div>
        )}

        {/* Explore */}
        {mounted.has('explore') && (
          <div className={tab === 'explore' ? '' : 'hidden'}>
            <div className="xc" style={{ padding: 24 }}>
              <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--t2)' }}>
                Tell me about yourself and I'll match you with STEM fields:
              </p>
              <ChatInterface onDeepDive={handleDeepDive} />
            </div>
          </div>
        )}

        {/* Deep Dive */}
        {mounted.has('deepdive') && (
          <div className={tab === 'deepdive' ? '' : 'hidden'}>
            <div className="xc" style={{ padding: 24 }}>
              {deepDiveFieldId ? (
                <DeepDivePage fieldId={deepDiveFieldId} onBack={handleBackFromDeepDive} />
              ) : (
                <div style={{ textAlign: 'center', padding: '48px 0' }}>
                  <p style={{ fontSize: 13, color: 'var(--t2)', margin: 0 }}>
                    Use the{' '}
                    <strong style={{ color: 'var(--t1)' }}>Explore</strong>{' '}
                    tab to find fields, then click{' '}
                    <strong style={{ color: 'var(--t1)' }}>Deep dive →</strong>{' '}
                    on any recommendation.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <footer style={{
        borderTop: '1px solid var(--bdr)',
        padding: '20px 24px',
        textAlign: 'center',
        fontSize: 11,
        color: 'var(--t3)',
        letterSpacing: '0.03em',
      }}>
        Salary data: BLS Occupational Outlook Handbook · AI summaries via Claude · Data sourced and cited per field
      </footer>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { fetchDeepDive } from '../api';
import type { DirectResponse } from '../types';

interface DeepDivePageProps {
  fieldId: string;
  onBack: () => void;
}

export default function DeepDivePage({ fieldId, onBack }: DeepDivePageProps) {
  const [data, setData] = useState<DirectResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);

    fetchDeepDive(fieldId).then((result) => {
      setLoading(false);
      if (result.ok) {
        setData(result.data);
      } else {
        setError(result.message);
      }
    });
  }, [fieldId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-400">
        <svg className="animate-spin h-8 w-8 mb-3 text-indigo-400" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <p className="text-sm">Generating deep dive…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
        <p className="text-sm text-red-700 mb-3">{error}</p>
        <button onClick={onBack} className="text-sm text-indigo-600 hover:underline">
          ← Back
        </button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <button
        onClick={onBack}
        className="text-sm text-indigo-600 hover:underline mb-4 inline-flex items-center gap-1"
      >
        ← Back
      </button>

      <h2 className="text-2xl font-bold text-slate-900 mb-1">{data.name}</h2>
      <p className="text-xs text-slate-400 uppercase tracking-wide mb-6">Deep Dive</p>

      <div className="flex flex-col gap-5">
        {data.sections.map((section) => (
          <div key={section.title} className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-semibold text-slate-800 text-sm mb-2">{section.title}</h3>
            <p className="text-sm text-slate-600 leading-relaxed">{section.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

import { useState, useRef, useEffect } from 'react';
import type { FieldSummary } from '../types';

interface Props {
  index: number;
  value: string;
  fields: FieldSummary[];
  selected: string[];
  onChange: (value: string) => void;
  onClear: () => void;
}

export default function FieldAutocomplete({ index, value, fields, selected, onChange, onClear }: Props) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const chosen = fields.find((f) => f.field_id === value);

  const filtered = fields.filter((f) => {
    if (selected.includes(f.field_id) && f.field_id !== value) return false;
    const q = query.toLowerCase();
    return f.name.toLowerCase().includes(q) || f.field_id.includes(q);
  });

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  function select(fieldId: string) {
    onChange(fieldId);
    setQuery('');
    setOpen(false);
  }

  function clear() {
    onClear();
    setQuery('');
    setOpen(false);
  }

  const labels = ['First field', 'Second field', 'Third field (optional)'];

  return (
    <div ref={ref} className="relative w-full">
      <label className="block text-xs font-medium text-slate-500 mb-1">{labels[index]}</label>

      {chosen ? (
        <div className="flex items-center justify-between px-3 py-2.5 bg-indigo-50 border border-indigo-300 rounded-lg">
          <span className="text-sm font-medium text-indigo-800">{chosen.name}</span>
          <button
            onClick={clear}
            className="text-indigo-400 hover:text-indigo-700 text-lg leading-none ml-2"
            aria-label="Clear"
          >
            ×
          </button>
        </div>
      ) : (
        <input
          type="text"
          className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm
                     focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent
                     placeholder:text-slate-400 bg-white"
          placeholder={`Search fields…`}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
        />
      )}

      {open && !chosen && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-sm text-slate-400 italic">No matches</p>
          ) : (
            filtered.map((f) => (
              <button
                key={f.field_id}
                className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                onMouseDown={() => select(f.field_id)}
              >
                {f.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

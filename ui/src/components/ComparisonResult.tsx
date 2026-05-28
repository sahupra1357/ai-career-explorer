import { useState } from 'react';
import type { CompareSuccess, FieldEntry } from '../types';
import IntensityBar from './IntensityBar';

interface Props {
  result: CompareSuccess;
}

function fmt(n: number) {
  return '$' + (n / 1000).toFixed(0) + 'k';
}

function FieldColumn({ field }: { field: FieldEntry }) {
  const pf = field.personality_fit;
  const co = field.career_outcomes;

  return (
    <div className="space-y-6">
      {/* Plain English */}
      <p className="text-sm text-slate-600 leading-relaxed">{field.plain_english}</p>

      {/* Personality fit — FIRST per design doc */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Who thrives here</h4>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">{pf.fit_description}</p>
        <div className="space-y-1.5">
          <IntensityBar value={pf.math_intensity} label="Math" />
          <IntensityBar value={pf.lab_intensity} label="Lab / hands-on" />
          <IntensityBar value={pf.coding_intensity} label="Coding" />
          <IntensityBar value={pf.people_facing} label="People-facing" />
        </div>
      </section>

      {/* Salary */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Salary</h4>
        <p className="text-lg font-semibold text-slate-800">
          {fmt(co.salary_range.min)} – {fmt(co.salary_range.max)}
        </p>
        <p className="text-xs text-slate-400">{co.salary_range.region} · {co.salary_range.source_year}</p>
      </section>

      {/* Outlook */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">Job outlook</h4>
        <p className="text-sm text-slate-700">{co.outlook}</p>
      </section>

      {/* Sub-areas */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Sub-areas</h4>
        <ul className="space-y-2">
          {field.sub_areas.map((s) => (
            <li key={s.name}>
              <p className="text-sm font-medium text-slate-700">{s.name}</p>
              <p className="text-xs text-slate-500">{s.description}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* Roles */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Common roles</h4>
        <ul className="space-y-1">
          {co.common_roles.map((r) => (
            <li key={r} className="text-sm text-slate-700 flex items-start gap-1.5">
              <span className="text-indigo-400 mt-0.5">›</span> {r}
            </li>
          ))}
        </ul>
      </section>

      {/* Undergrad path */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Undergrad path</h4>
        <div className="space-y-2 text-sm">
          <div>
            <p className="text-xs text-slate-400 font-medium mb-1">High school prereqs</p>
            <ul className="space-y-0.5">
              {field.undergrad_path.high_school_prereqs.map((p) => (
                <li key={p} className="text-slate-600 flex gap-1.5">
                  <span className="text-slate-300">·</span> {p}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs text-slate-400 font-medium mb-1">Common majors</p>
            <ul className="space-y-0.5">
              {field.undergrad_path.common_majors.map((m) => (
                <li key={m} className="text-slate-600 flex gap-1.5">
                  <span className="text-slate-300">·</span> {m}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Follow-on questions */}
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Questions to explore</h4>
        <ul className="space-y-1.5">
          {field.follow_on_questions.map((q) => (
            <li key={q} className="text-sm text-slate-600 italic">{q}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function ComparisonResult({ result }: Props) {
  const [activeTab, setActiveTab] = useState(0);
  const { fields, comparison_summary, summary_status } = result;

  return (
    <div className="mt-6 space-y-6">
      {/* Summary headline — pinned at top per design doc */}
      <div className={`rounded-xl p-5 ${summary_status === 'ready' && comparison_summary
        ? 'bg-indigo-50 border border-indigo-200'
        : 'bg-slate-100 border border-slate-200'
      }`}>
        {summary_status === 'ready' && comparison_summary ? (
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-500 mb-2">AI insight</p>
            <p className="text-base text-indigo-900 leading-relaxed font-medium">{comparison_summary}</p>
          </>
        ) : (
          <p className="text-sm text-slate-500 italic">Summary unavailable — Claude did not respond in time.</p>
        )}
      </div>

      {/* Desktop: side-by-side columns */}
      <div className="hidden md:grid gap-6" style={{ gridTemplateColumns: `repeat(${fields.length}, 1fr)` }}>
        {fields.map((f) => (
          <div key={f.field_id} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-4 pb-3 border-b border-slate-100">{f.name}</h3>
            <FieldColumn field={f} />
          </div>
        ))}
      </div>

      {/* Mobile: tab strip per design doc */}
      <div className="md:hidden">
        <div className="flex border-b border-slate-200 overflow-x-auto">
          {fields.map((f, i) => (
            <button
              key={f.field_id}
              onClick={() => setActiveTab(i)}
              className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === i
                  ? 'border-indigo-500 text-indigo-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>
        <div className="bg-white rounded-b-xl border border-t-0 border-slate-200 p-5 shadow-sm">
          <FieldColumn field={fields[activeTab]} />
        </div>
      </div>
    </div>
  );
}

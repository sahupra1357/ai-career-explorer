import { useState } from 'react';
import { searchCoursesStream, type SearchProgress } from '../api';
import {
  DECISION_FIELDS,
  DEFAULT_PRIORITIES,
  evidenceFor,
  gapChips,
  officialLink,
  priorityStatuses,
  readinessSummary,
  yearOf,
} from '../decision';
import type { CourseSearchResponse, MoneyAmount, RankedProgram } from '../types';

type SearchState =
  | { phase: 'idle' }
  | { phase: 'loading'; progress: SearchProgress }
  | { phase: 'success'; data: CourseSearchResponse }
  | { phase: 'error'; message: string };

function progressPct(p: SearchProgress): number {
  if (p.phase === 'investigating' && p.total) {
    return Math.min(96, 10 + Math.round((p.done! / p.total) * 86));
  }
  if (p.phase === 'seeded') return 10;
  return 5;
}

function progressLabel(p: SearchProgress): string {
  if (p.phase === 'seeded') return `Found ${p.total} colleges — dispatching research agents…`;
  if (p.phase === 'investigating') return `Investigating ${p.done} of ${p.total} colleges…`;
  return 'Finding colleges…';
}

const STATES: [string, string][] = [
  ['AL', 'Alabama'], ['AK', 'Alaska'], ['AZ', 'Arizona'], ['AR', 'Arkansas'],
  ['CA', 'California'], ['CO', 'Colorado'], ['CT', 'Connecticut'], ['DE', 'Delaware'],
  ['DC', 'District of Columbia'], ['FL', 'Florida'], ['GA', 'Georgia'], ['HI', 'Hawaii'],
  ['ID', 'Idaho'], ['IL', 'Illinois'], ['IN', 'Indiana'], ['IA', 'Iowa'], ['KS', 'Kansas'],
  ['KY', 'Kentucky'], ['LA', 'Louisiana'], ['ME', 'Maine'], ['MD', 'Maryland'],
  ['MA', 'Massachusetts'], ['MI', 'Michigan'], ['MN', 'Minnesota'], ['MS', 'Mississippi'],
  ['MO', 'Missouri'], ['MT', 'Montana'], ['NE', 'Nebraska'], ['NV', 'Nevada'],
  ['NH', 'New Hampshire'], ['NJ', 'New Jersey'], ['NM', 'New Mexico'], ['NY', 'New York'],
  ['NC', 'North Carolina'], ['ND', 'North Dakota'], ['OH', 'Ohio'], ['OK', 'Oklahoma'],
  ['OR', 'Oregon'], ['PA', 'Pennsylvania'], ['RI', 'Rhode Island'], ['SC', 'South Carolina'],
  ['SD', 'South Dakota'], ['TN', 'Tennessee'], ['TX', 'Texas'], ['UT', 'Utah'],
  ['VT', 'Vermont'], ['VA', 'Virginia'], ['WA', 'Washington'], ['WV', 'West Virginia'],
  ['WI', 'Wisconsin'], ['WY', 'Wyoming'],
];

function money(item: MoneyAmount | null) {
  if (!item) return 'Check source';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: item.currency,
    maximumFractionDigits: 0,
  }).format(item.amount);
}

function ProgramCard({ ranked, priorities }: { ranked: RankedProgram; priorities: Set<string> }) {
  const { program, distance_miles, match_reason } = ranked;
  const distance = distance_miles === null ? null : `${Math.round(distance_miles)} mi`;
  const link = officialLink(program);
  const statuses = priorityStatuses(program, priorities);
  const verifiedCount = statuses.filter((s) => s.verified).length;
  const gaps = gapChips(program);
  const tuitionAsOf = yearOf(evidenceFor(program, 'fees')?.as_of);

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-slate-950">{program.college_name}</h3>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
              {program.city}, {program.state}
            </span>
            {distance && (
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                {distance}
              </span>
            )}
            {program.carnegie_classification && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                {program.carnegie_classification.split(':')[0]}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm font-medium text-slate-700">{program.degree}</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{program.overview}</p>
        </div>
        <div className="min-w-44 rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-semibold uppercase text-slate-400">Estimated tuition</p>
          <p className="mt-2 text-sm text-slate-700">In-state: <strong>{money(program.fees.in_state_tuition)}</strong></p>
          <p className="text-sm text-slate-700">Out-of-state: <strong>{money(program.fees.out_of_state_tuition)}</strong></p>
          {tuitionAsOf && <p className="mt-1 text-[11px] text-slate-400">College Scorecard · as of {tuitionAsOf}</p>}
        </div>
      </div>

      {statuses.length > 0 && (
        <div className="mt-4 rounded-md border border-cyan-100 bg-cyan-50/60 p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-cyan-900">Decision readiness</p>
            <span className="text-xs font-medium text-cyan-800">
              {verifiedCount} of {statuses.length} of your priorities verified
            </span>
          </div>
          <ul className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {statuses.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <span className={s.verified ? 'text-emerald-600' : 'text-amber-500'}>{s.verified ? '✓' : '⚠'}</span>
                  {s.label}
                </span>
                {s.verified ? (
                  s.sourceLabel &&
                  (s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer"
                      className="shrink-0 rounded bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200 hover:text-cyan-700">
                      {s.sourceLabel}{s.asOf ? ` · ${s.asOf}` : ''} ↗
                    </a>
                  ) : (
                    <span className="shrink-0 rounded bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200">
                      {s.sourceLabel}{s.asOf ? ` · ${s.asOf}` : ''}
                    </span>
                  ))
                ) : s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer"
                    className="shrink-0 text-[11px] font-medium text-amber-700 hover:underline">verify on site →</a>
                ) : (
                  <span className="shrink-0 text-[11px] font-medium text-amber-700">verify on site</span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs leading-5 text-slate-600">{readinessSummary(statuses)}</p>
        </div>
      )}

      {gaps.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {gaps.map((g, i) =>
            g.url ? (
              <a key={i} href={g.url} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200 hover:ring-amber-300">
                ⚠ {g.label} ↗
              </a>
            ) : (
              <span key={i} className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
                ⚠ {g.label}
              </span>
            ),
          )}
        </div>
      )}

      <div className="mt-5 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Course structure</h4>
          <p className="mt-2 text-sm leading-6 text-slate-700">{program.curriculum_summary}</p>
          {link && (
            <a
              href={link}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-cyan-700 hover:text-cyan-800 hover:underline"
            >
              View official program page →
            </a>
          )}
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {program.semester_plan.map((term) => (
              <div key={term.term} className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-sm font-semibold text-slate-800">{term.term}</p>
                <p className="text-xs text-slate-500">{term.focus}</p>
                <ul className="mt-2 space-y-1">
                  {term.courses.slice(0, 4).map((course) => (
                    <li key={course} className="text-xs text-slate-600">{course}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Required papers</h4>
            <ul className="mt-2 space-y-1.5">
              {program.required_papers.map((paper) => (
                <li key={paper} className="text-sm text-slate-700">{paper}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Admission factors</h4>
            <ul className="mt-2 space-y-1.5">
              {program.admission_factors.map((factor) => (
                <li key={factor} className="text-sm text-slate-700">{factor}</li>
              ))}
            </ul>
          </div>
        </section>
      </div>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Counselor read</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">
          {match_reason}. {program.decision_factors.join(' · ')}
        </p>
        <p className="mt-2 text-xs text-slate-500">{program.fees.notes}</p>

        <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">Sources &amp; verification</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {program.sources.map((source) => (
            <a
              key={source.url}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:border-cyan-300 hover:text-cyan-700"
            >
              {source.label}
            </a>
          ))}
          <a
            href={program.fees.source_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:border-cyan-300 hover:text-cyan-700"
          >
            Cost source
          </a>
          {program.rankings.map((r) => (
            <a
              key={r.url}
              href={r.url}
              target="_blank"
              rel="noreferrer"
              title={r.note}
              className="rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:border-cyan-300 hover:text-cyan-700"
            >
              {r.name}
            </a>
          ))}
        </div>
      </div>
    </article>
  );
}

export default function CourseFinder() {
  const [course, setCourse] = useState('Computer Science');
  const [city, setCity] = useState('Philadelphia');
  const [state, setState] = useState('PA');
  const [homeState, setHomeState] = useState('PA');
  const [searchState, setSearchState] = useState<SearchState>({ phase: 'idle' });
  const [priorities, setPriorities] = useState<Set<string>>(new Set(DEFAULT_PRIORITIES));

  function togglePriority(id: string) {
    setPriorities((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function submit() {
    if (course.trim().length < 2 || searchState.phase === 'loading') return;
    setSearchState({ phase: 'loading', progress: { phase: 'starting' } });
    const result = await searchCoursesStream(
      {
        course_query: course,
        city: city || undefined,
        state: state || undefined,
        home_state: homeState || undefined,
      },
      (progress) =>
        setSearchState((prev) => (prev.phase === 'loading' ? { phase: 'loading', progress } : prev)),
    );
    setSearchState(result.ok ? { phase: 'success', data: result.data } : { phase: 'error', message: result.message });
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-[1.2fr_1fr_120px_150px_auto] md:items-end">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Course</span>
            <input
              value={course}
              onChange={(event) => setCourse(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              placeholder="Computer Science"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">City</span>
            <input
              value={city}
              onChange={(event) => setCity(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              placeholder="Berkeley"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">State</span>
            <select
              value={state}
              onChange={(event) => setState(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            >
              {STATES.map(([code, name]) => <option key={code} value={code}>{code} — {name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Home state</span>
            <select
              value={homeState}
              onChange={(event) => setHomeState(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            >
              {STATES.map(([code, name]) => <option key={code} value={code}>{code} — {name}</option>)}
            </select>
          </label>
          <button
            onClick={submit}
            disabled={searchState.phase === 'loading' || course.trim().length < 2}
            className="rounded-lg bg-cyan-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-cyan-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {searchState.phase === 'loading' ? 'Searching' : 'Find'}
          </button>
        </div>
      </section>

      {searchState.phase === 'idle' && (
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-950">Start with a course, then compare colleges by evidence.</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            The result groups programs by distance and residency logic, then shows curriculum structure, application papers,
            fee context, and official links so a family can verify the details before shortlisting.
          </p>
        </section>
      )}

      {searchState.phase === 'loading' && (
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-800">{progressLabel(searchState.progress)}</p>
            <span className="text-xs font-medium text-slate-400">{progressPct(searchState.progress)}%</span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-cyan-600 transition-all duration-500 ease-out"
              style={{ width: `${progressPct(searchState.progress)}%` }}
            />
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">
            Research agents are reading each college’s official program pages and extracting the
            curriculum, admissions, and fees. This can take up to a minute.
          </p>
        </section>
      )}

      {searchState.phase === 'error' && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {searchState.message}
        </div>
      )}

      {searchState.phase === 'success' && (
        <div className="space-y-6">
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4">
            <p className="text-sm font-semibold text-cyan-950">
              {searchState.data.query} near {searchState.data.location_used}
            </p>
            <ul className="mt-2 grid gap-2 md:grid-cols-3">
              {searchState.data.guidance.map((item) => (
                <li key={item} className="text-xs leading-5 text-cyan-900">{item}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">What matters most to you?</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {DECISION_FIELDS.map((field) => {
                const on = priorities.has(field.id);
                return (
                  <button
                    key={field.id}
                    onClick={() => togglePriority(field.id)}
                    className={
                      on
                        ? 'rounded-full bg-cyan-600 px-3 py-1 text-xs font-medium text-white'
                        : 'rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200'
                    }
                  >
                    {field.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-slate-400">
              Each college shows how many of these are verified (with their source) and what’s left to confirm.
            </p>
          </div>

          {searchState.data.tiers.map((tier) => (
            <section key={tier.tier} className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-950">{tier.title}</h2>
                <span className="text-xs font-medium text-slate-400">{tier.programs.length} options</span>
              </div>
              {tier.programs.length > 0 ? (
                <div className="space-y-4">
                  {tier.programs.map((ranked) => (
                    <ProgramCard key={ranked.program.program_id} ranked={ranked} priorities={priorities} />
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-slate-200 bg-white p-5 text-sm text-slate-500">
                  No matching programs in this tier yet.
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

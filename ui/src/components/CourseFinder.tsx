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
  const [open, setOpen] = useState(false);
  const { program, distance_miles, match_reason } = ranked;
  const distance = distance_miles === null ? null : `${Math.round(distance_miles)} mi`;
  const link = officialLink(program);
  const statuses = priorityStatuses(program, priorities);
  const verifiedCount = statuses.filter((s) => s.verified).length;
  const allVerified = statuses.length > 0 && verifiedCount === statuses.length;
  const gaps = gapChips(program);
  const tuitionAsOf = yearOf(evidenceFor(program, 'fees')?.as_of);

  return (
    <article
      className="xc"
      style={{
        overflow: 'hidden',
        transition: 'border-color 0.15s',
        borderColor: open ? 'var(--bdr2)' : undefined,
      }}
    >
      {/* Collapsed header — always visible */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="xcard-btn"
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          padding: '16px 20px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          transition: 'background 0.12s',
        }}
      >
        {/* Left: name + degree */}
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontFamily: 'var(--fb)',
              fontSize: 16,
              fontWeight: 600,
              color: 'var(--t1)',
            }}>
              {program.college_name}
            </span>
            <span className="xbadge xbadge-grey">{program.city}, {program.state}</span>
            {distance && (
              <span className="xbadge" style={{ background: 'rgba(41,160,126,0.12)', color: 'var(--teal)' }}>
                {distance}
              </span>
            )}
            {program.carnegie_classification && (
              <span className="xbadge xbadge-grey">
                {program.carnegie_classification.split(':')[0]}
              </span>
            )}
          </div>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--t2)', fontWeight: 400 }}>
            {program.degree}
          </p>
        </div>

        {/* Right: verified badge + chevron */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {statuses.length > 0 && (
            <span
              className="xbadge"
              style={allVerified
                ? { background: 'var(--teal-bg)', color: 'var(--teal)' }
                : { background: 'var(--amber-bg)', color: 'var(--amber-lt)' }
              }
            >
              {verifiedCount}/{statuses.length} verified
            </span>
          )}
          <svg
            style={{
              width: 18,
              height: 18,
              color: 'var(--t3)',
              transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s',
              flexShrink: 0,
            }}
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="m6 8 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </button>

      {/* Expanded detail */}
      {open && (
        <div style={{ borderTop: '1px solid var(--bdr)' }}>

          {/* Overview + tuition */}
          <div style={{ padding: '20px 20px 0', display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
            <p style={{ flex: '1 1 300px', margin: 0, fontSize: 13, lineHeight: 1.7, color: 'var(--t2)' }}>
              {program.overview}
            </p>
            <div style={{
              flexShrink: 0,
              minWidth: 180,
              background: 'var(--s2)',
              border: '1px solid var(--bdr)',
              borderRadius: 8,
              padding: '12px 16px',
            }}>
              <p className="xsec" style={{ margin: '0 0 8px' }}>Estimated tuition</p>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--t2)' }}>
                In-state: <strong style={{ color: 'var(--t1)' }}>{money(program.fees.in_state_tuition)}</strong>
              </p>
              <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--t2)' }}>
                Out-of-state: <strong style={{ color: 'var(--t1)' }}>{money(program.fees.out_of_state_tuition)}</strong>
              </p>
              {tuitionAsOf && (
                <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--t3)' }}>
                  College Scorecard · as of {tuitionAsOf}
                </p>
              )}
            </div>
          </div>

          {/* Decision readiness */}
          {statuses.length > 0 && (
            <div style={{
              margin: '16px 20px 0',
              background: 'var(--s2)',
              border: '1px solid var(--bdr)',
              borderRadius: 10,
              padding: '14px 16px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                <p className="xsec" style={{ margin: 0 }}>Decision readiness</p>
                <span style={{ fontSize: 12, fontWeight: 600, color: allVerified ? 'var(--teal)' : 'var(--amber-lt)' }}>
                  {verifiedCount} of {statuses.length} of your priorities verified
                </span>
              </div>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: '8px 24px', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
                {statuses.map((s) => (
                  <li key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--t1)' }}>
                      <span style={{ color: s.verified ? 'var(--teal)' : 'var(--warn)', fontSize: 14 }}>
                        {s.verified ? '✓' : '⚠'}
                      </span>
                      {s.label}
                    </span>
                    {s.verified ? (
                      s.sourceLabel && (
                        s.url ? (
                          <a href={s.url} target="_blank" rel="noreferrer" className="xsrc">
                            {s.sourceLabel}{s.asOf ? ` · ${s.asOf}` : ''} ↗
                          </a>
                        ) : (
                          <span className="xsrc">{s.sourceLabel}{s.asOf ? ` · ${s.asOf}` : ''}</span>
                        )
                      )
                    ) : (
                      s.url
                        ? <a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--warn)', textDecoration: 'none' }}>verify →</a>
                        : <span style={{ fontSize: 11, color: 'var(--warn)' }}>verify on site</span>
                    )}
                  </li>
                ))}
              </ul>
              <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--t2)' }}>{readinessSummary(statuses)}</p>
            </div>
          )}

          {/* Gap chips */}
          {gaps.length > 0 && (
            <div style={{ margin: '12px 20px 0', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {gaps.map((g, i) =>
                g.url ? (
                  <a key={i} href={g.url} target="_blank" rel="noreferrer"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 12px', borderRadius: 99, fontSize: 11, fontWeight: 500, background: 'var(--warn-bg)', color: 'var(--warn)', textDecoration: 'none', outline: '1px solid rgba(200,120,40,0.25)', outlineOffset: -1 }}>
                    ⚠ {g.label} ↗
                  </a>
                ) : (
                  <span key={i}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 12px', borderRadius: 99, fontSize: 11, fontWeight: 500, background: 'var(--warn-bg)', color: 'var(--warn)', outline: '1px solid rgba(200,120,40,0.25)', outlineOffset: -1 }}>
                    ⚠ {g.label}
                  </span>
                )
              )}
            </div>
          )}

          {/* Course structure + papers + factors */}
          <div style={{ margin: '16px 20px 0', display: 'grid', gridTemplateColumns: '1fr auto', gap: '0 32px' }}>
            <section>
              <p className="xsec">Course structure</p>
              <p style={{ margin: '0 0 8px', fontSize: 13, lineHeight: 1.7, color: 'var(--t2)' }}>
                {program.curriculum_summary}
              </p>
              {link && (
                <a href={link} target="_blank" rel="noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, fontWeight: 500, color: 'var(--amber-lt)', textDecoration: 'none' }}>
                  View official program page →
                </a>
              )}
              {program.semester_plan.length > 0 && (
                <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8 }}>
                  {program.semester_plan.map((term) => (
                    <div key={term.term}
                      style={{ background: 'var(--s2)', border: '1px solid var(--bdr)', borderRadius: 8, padding: 12 }}>
                      <p style={{ margin: '0 0 2px', fontSize: 12, fontWeight: 600, color: 'var(--t1)' }}>{term.term}</p>
                      <p style={{ margin: '0 0 6px', fontSize: 11, color: 'var(--t3)' }}>{term.focus}</p>
                      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                        {term.courses.slice(0, 4).map((c) => (
                          <li key={c} style={{ fontSize: 11, color: 'var(--t2)', paddingBottom: 2 }}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section style={{ minWidth: 180, maxWidth: 220 }}>
              <div style={{ marginBottom: 20 }}>
                <p className="xsec">Required papers</p>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {program.required_papers.map((p) => (
                    <li key={p} style={{ fontSize: 13, color: 'var(--t2)', paddingBottom: 4 }}>{p}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="xsec">Admission factors</p>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {program.admission_factors.map((f) => (
                    <li key={f} style={{ fontSize: 13, color: 'var(--t2)', paddingBottom: 4 }}>{f}</li>
                  ))}
                </ul>
              </div>
            </section>
          </div>

          {/* Counselor read + sources */}
          <div style={{ margin: '16px 20px 0', paddingTop: 16, borderTop: '1px solid var(--bdr)' }}>
            <p className="xsec">Counselor read</p>
            <p style={{ margin: '0 0 4px', fontSize: 13, lineHeight: 1.7, color: 'var(--t2)' }}>
              {match_reason}. {program.decision_factors.join(' · ')}
            </p>
            {program.fees.notes && (
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--t3)' }}>{program.fees.notes}</p>
            )}

            <p className="xsec" style={{ marginTop: 14 }}>Sources &amp; verification</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingBottom: 20 }}>
              {program.sources.map((src) => (
                <a key={src.url} href={src.url} target="_blank" rel="noreferrer" className="xsrc">
                  {src.label}
                </a>
              ))}
              <a href={program.fees.source_url} target="_blank" rel="noreferrer" className="xsrc">
                Cost source
              </a>
              {program.rankings.map((r) => (
                <a key={r.url} href={r.url} target="_blank" rel="noreferrer" title={r.note} className="xsrc">
                  {r.name}
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
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
      { course_query: course, city: city || undefined, state: state || undefined, home_state: homeState || undefined },
      (progress) => setSearchState((prev) => (prev.phase === 'loading' ? { phase: 'loading', progress } : prev)),
    );
    setSearchState(result.ok ? { phase: 'success', data: result.data } : { phase: 'error', message: result.message });
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* Search form */}
      <section className="xc" style={{ padding: 20 }}>
        <form
          onSubmit={(e) => { e.preventDefault(); submit(); }}
          style={{ display: 'grid', gap: 12, gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr) auto auto auto', alignItems: 'end' }}
        >
          <label>
            <span className="xl">Course or program</span>
            <input
              value={course}
              onChange={(e) => setCourse(e.target.value)}
              className="xi"
              placeholder="Computer Science"
            />
          </label>
          <label>
            <span className="xl">City</span>
            <input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="xi"
              placeholder="Philadelphia"
            />
          </label>
          <label>
            <span className="xl">State</span>
            <select value={state} onChange={(e) => setState(e.target.value)} className="xi" title="State to search in" style={{ width: 76 }}>
              {STATES.map(([code, name]) => <option key={code} value={code} title={name}>{code}</option>)}
            </select>
          </label>
          <label>
            <span className="xl">Home state</span>
            <select value={homeState} onChange={(e) => setHomeState(e.target.value)} className="xi" title="Your residency — used to estimate in-state tuition" style={{ width: 76 }}>
              {STATES.map(([code, name]) => <option key={code} value={code} title={name}>{code}</option>)}
            </select>
          </label>
          <div style={{ paddingTop: 18 }}>
            <button type="submit" disabled={searchState.phase === 'loading' || course.trim().length < 2} className="xbtn">
              {searchState.phase === 'loading' ? (
                <>
                  <svg style={{ width: 16, height: 16, animation: 'spin 1s linear infinite' }} viewBox="0 0 24 24" fill="none">
                    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path opacity=".75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Searching
                </>
              ) : (
                <>
                  <svg style={{ width: 15, height: 15 }} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="9" cy="9" r="6" /><path d="m14 14 3 3" strokeLinecap="round" />
                  </svg>
                  Find
                </>
              )}
            </button>
          </div>
        </form>
        <p style={{ margin: '10px 0 0', fontSize: 11, color: 'var(--t3)' }}>
          <span style={{ color: 'var(--t2)', fontWeight: 500 }}>State</span> sets search location ·{' '}
          <span style={{ color: 'var(--t2)', fontWeight: 500 }}>Home state</span> estimates in-state tuition
        </p>
      </section>

      {/* Idle */}
      {searchState.phase === 'idle' && (
        <section className="xc" style={{ padding: 24 }}>
          <h2 style={{ margin: '0 0 8px', fontFamily: 'var(--fd)', fontSize: 20, fontWeight: 600, color: 'var(--t1)', letterSpacing: '-0.01em' }}>
            Start with a course, then compare colleges by evidence.
          </h2>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.75, color: 'var(--t2)', maxWidth: 640 }}>
            Results are grouped by proximity and residency. Each college shows curriculum structure,
            admission requirements, fee context, and official links so you can verify before shortlisting.
          </p>
        </section>
      )}

      {/* Loading */}
      {searchState.phase === 'loading' && (
        <section className="xc" style={{ padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: 'var(--t1)' }}>
              {progressLabel(searchState.progress)}
            </p>
            <span style={{ fontSize: 12, color: 'var(--t3)', fontWeight: 600 }}>
              {progressPct(searchState.progress)}%
            </span>
          </div>
          <div className="xprog-track">
            <div className="xprog-fill" style={{ width: `${progressPct(searchState.progress)}%` }} />
          </div>
          <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--t3)', lineHeight: 1.6 }}>
            Research agents are reading each college's official program pages and extracting
            curriculum, admissions, and fees. This can take up to a minute.
          </p>
        </section>
      )}

      {/* Error */}
      {searchState.phase === 'error' && (
        <div style={{ background: 'rgba(180,60,50,0.1)', border: '1px solid rgba(180,60,50,0.25)', borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#e07070' }}>
          {searchState.message}
        </div>
      )}

      {/* Results */}
      {searchState.phase === 'success' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>

          {/* Guidance */}
          <div style={{
            background: 'var(--s1)',
            border: '1px solid rgba(200,133,42,0.2)',
            borderLeft: '3px solid var(--amber)',
            borderRadius: 10,
            overflow: 'hidden',
          }}>
            <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--bdr)', display: 'flex', alignItems: 'center', gap: 10 }}>
              <svg style={{ width: 16, height: 16, color: 'var(--amber)', flexShrink: 0 }} viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--t1)' }}>
                {searchState.data.query} near {searchState.data.location_used}
              </p>
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
              {searchState.data.guidance.map((item, i) => (
                <li key={item} style={{
                  display: 'flex',
                  gap: 10,
                  padding: '12px 18px',
                  borderTop: i > 0 ? '1px solid var(--bdr)' : undefined,
                  borderLeft: i > 0 ? '1px solid var(--bdr)' : undefined,
                }}>
                  <svg style={{ marginTop: 2, width: 13, height: 13, flexShrink: 0, color: 'var(--amber)' }} viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.7-9.3a1 1 0 00-1.4-1.4L9 10.6 7.7 9.3a1 1 0 00-1.4 1.4l2 2a1 1 0 001.4 0l4-4z" clipRule="evenodd" />
                  </svg>
                  <span style={{ fontSize: 12, lineHeight: 1.6, color: 'var(--t2)' }}>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Priority chips */}
          <div className="xc" style={{ padding: '16px 20px' }}>
            <p className="xsec" style={{ marginBottom: 10 }}>What matters most to you?</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {DECISION_FIELDS.map((field) => {
                const on = priorities.has(field.id);
                return (
                  <button
                    key={field.id}
                    onClick={() => togglePriority(field.id)}
                    className={`xchip ${on ? 'xchip-on' : 'xchip-off'}`}
                  >
                    {field.label}
                  </button>
                );
              })}
            </div>
            <p style={{ margin: '10px 0 0', fontSize: 11, color: 'var(--t3)' }}>
              Each college shows how many of these are verified (with their source) and what's left to confirm.
            </p>
          </div>

          {/* Tiers */}
          {searchState.data.tiers.map((tier) => (
            <section key={tier.tier}>
              <div className="xtier">
                <h2 className="xtier-title">{tier.title}</h2>
                <div className="xtier-line" />
                <span className="xtier-count">{tier.programs.length} option{tier.programs.length !== 1 ? 's' : ''}</span>
              </div>
              {tier.programs.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {tier.programs.map((ranked) => (
                    <ProgramCard key={ranked.program.program_id} ranked={ranked} priorities={priorities} />
                  ))}
                </div>
              ) : (
                <div style={{
                  background: 'var(--s1)',
                  border: '1px dashed var(--bdr2)',
                  borderRadius: 10,
                  padding: '20px',
                  fontSize: 13,
                  color: 'var(--t3)',
                  textAlign: 'center',
                }}>
                  No matching programs in this tier.
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

import type { CollegeProgram, ProgramEvidence } from './types';

// ── Decision fields: what a student can mark as a priority, and how we tell whether the
//    college's data for it is actually VERIFIED (from a real source) vs still unknown. ──

export interface DecisionField {
  id: string;
  label: string;
  claimType?: string; // evidence claim_type that backs this field
  verified: (p: CollegeProgram) => boolean;
}

const includesAny = (arr: string[] | undefined, needle: string) =>
  (arr ?? []).some((s) => s.toLowerCase().includes(needle));

export function evidenceFor(p: CollegeProgram, claimType: string): ProgramEvidence | undefined {
  return (p.evidence ?? []).find((e) => e.claim_type === claimType);
}

export const DECISION_FIELDS: DecisionField[] = [
  {
    id: 'curriculum',
    label: 'Curriculum & courses',
    claimType: 'curriculum',
    verified: (p) => !(p.data_quality_flags ?? []).includes('missing_curriculum_source'),
  },
  {
    id: 'cost',
    label: 'Tuition & cost',
    claimType: 'fees',
    verified: (p) => !!(p.fees.in_state_tuition || p.fees.out_of_state_tuition),
  },
  {
    id: 'admission',
    label: 'Admission criteria',
    claimType: 'admissions',
    verified: (p) => evidenceFor(p, 'admissions') !== undefined || includesAny(p.admission_factors, 'rate'),
  },
  {
    id: 'outcomes',
    label: 'Outcomes (grad rate, salary)',
    claimType: 'outcomes',
    verified: (p) =>
      evidenceFor(p, 'outcomes') !== undefined ||
      includesAny(p.decision_factors, 'graduation') ||
      includesAny(p.decision_factors, 'earnings'),
  },
  {
    id: 'aid',
    label: 'Net price / financial aid',
    verified: (p) => includesAny(p.decision_factors, 'net price'),
  },
  {
    id: 'deadline',
    label: 'Application deadline',
    verified: (p) => includesAny(p.admission_factors, 'deadline') || includesAny(p.required_papers, 'deadline'),
  },
];

export const DEFAULT_PRIORITIES = ['curriculum', 'cost', 'admission', 'outcomes'];

export function officialLink(p: CollegeProgram): string | undefined {
  return (
    p.sources.find((s) => /official/i.test(s.label))?.url ??
    p.sources[0]?.url ??
    p.fees.source_url
  );
}

export function yearOf(asOf: string | undefined): string {
  const y = (asOf ?? '').slice(0, 4);
  return /^\d{4}$/.test(y) ? y : '';
}

export interface FieldStatus {
  id: string;
  label: string;
  verified: boolean;
  sourceLabel?: string;
  asOf?: string;
  url?: string;
}

export function fieldStatus(p: CollegeProgram, field: DecisionField): FieldStatus {
  const verified = field.verified(p);
  const ev = field.claimType ? evidenceFor(p, field.claimType) : undefined;
  return {
    id: field.id,
    label: field.label,
    verified,
    sourceLabel: verified ? ev?.source_label : undefined,
    asOf: verified ? yearOf(ev?.as_of) : undefined,
    url: ev?.source_url || officialLink(p),
  };
}

export function priorityStatuses(p: CollegeProgram, priorities: Set<string>): FieldStatus[] {
  return DECISION_FIELDS.filter((f) => priorities.has(f.id)).map((f) => fieldStatus(p, f));
}

export function readinessSummary(statuses: FieldStatus[]): string {
  const total = statuses.length;
  if (total === 0) return 'Pick what matters to you above to see how ready you are to decide.';
  const verified = statuses.filter((s) => s.verified).length;
  const missing = statuses.filter((s) => !s.verified).map((s) => s.label.toLowerCase());
  if (verified === total) return 'Every priority you picked is verified — you have what you need to compare.';
  if (verified / total >= 0.8) return `Mostly there — confirm ${missing.join(', ')} before applying.`;
  return `Still missing key info: ${missing.join(', ')}.`;
}

// ── Honest-gap chips from data_quality_flags. ──
const GAP_LABELS: Record<string, string> = {
  missing_curriculum_source: 'Curriculum not verified — check the official program page',
  missing_fee_source: 'Fees unavailable — verify on the bursar page',
  fee_estimate_only: 'Fees are estimates — confirm cost of attendance',
  catalog_page_not_found: 'Official program page not found — verify on the college site',
  unofficial_ranking_source: 'Ranking is from an unofficial source',
  program_name_ambiguous: 'Program name is ambiguous — confirm the exact program',
  requires_manual_review: 'Some details need manual review',
};

export interface GapChip {
  label: string;
  url?: string;
}

export function gapChips(p: CollegeProgram): GapChip[] {
  const link = officialLink(p);
  return (p.data_quality_flags ?? [])
    .filter((f) => f in GAP_LABELS)
    .map((f) => ({ label: GAP_LABELS[f], url: link }));
}

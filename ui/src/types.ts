export interface FieldSummary {
  field_id: string;
  name: string;
}

export interface SubArea {
  name: string;
  description: string;
}

export interface UndergradPath {
  high_school_prereqs: string[];
  common_majors: string[];
  key_courses: string[];
}

export interface SalaryRange {
  min: number;
  max: number;
  currency: string;
  source_year: number;
  region: string;
}

export interface CareerOutcomes {
  common_roles: string[];
  salary_range: SalaryRange;
  outlook: string;
  outlook_pct: number | null;
}

export interface PersonalityFit {
  math_intensity: number;
  lab_intensity: number;
  coding_intensity: number;
  people_facing: number;
  fit_description: string;
}

export interface FieldEntry {
  schema_version: string;
  field_id: string;
  name: string;
  plain_english: string;
  sub_areas: SubArea[];
  undergrad_path: UndergradPath;
  career_outcomes: CareerOutcomes;
  personality_fit: PersonalityFit;
  adjacent_fields: string[];
  follow_on_questions: string[];
}

export interface CompareSuccess {
  request_id: string;
  fields: FieldEntry[];
  comparison_fields_used: string[];
  comparison_summary: string | null;
  summary_status: 'ready' | 'error';
}

export interface NotFoundError {
  request_id: string;
  error: 'not_found';
  message: string;
  suggestions: string[];
}

export interface PartialNotFoundError {
  request_id: string;
  error: 'partial_not_found';
  found: string[];
  not_found: string[];
  suggestions: Record<string, string[]>;
}

export type CompareError = NotFoundError | PartialNotFoundError;

// ── Phase 2: Explore ──────────────────────────────────────────────────────────

export interface RecommendedField {
  field_id: string;
  name: string;
  reason: string;
  score: number | null;
}

export interface ExploreResponse {
  session_id: string;
  reply: string;
  status: 'intake' | 'clarifying' | 'complete';
  recommended_fields: RecommendedField[];
}

// ── Phase 2: Direct (deep dive) ───────────────────────────────────────────────

export interface DeepDiveSection {
  title: string;
  content: string;
}

export interface DirectResponse {
  field_id: string;
  name: string;
  sections: DeepDiveSection[];
}

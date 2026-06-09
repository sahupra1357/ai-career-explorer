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

// ── Phase 3: Course Finder ───────────────────────────────────────────────────

export interface MoneyAmount {
  amount: number;
  currency: 'USD';
  label: string;
}

export interface ProgramSource {
  label: string;
  url: string;
}

export interface ProgramEvidence {
  claim_type: string;
  claim: string;
  source_url: string;
  source_label: string;
  as_of: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface RankingLink {
  name: string;
  url: string;
  note: string;
}

export interface LicensedRanking {
  provider: string;
  rank: number;
  list_name: string | null;
  year: number;
  source_url: string | null;
}

export interface SemesterPlan {
  term: string;
  focus: string;
  courses: string[];
}

export interface ProgramFees {
  in_state_tuition: MoneyAmount | null;
  out_of_state_tuition: MoneyAmount | null;
  mandatory_fees: MoneyAmount | null;
  notes: string;
  source_url: string;
}

export interface CollegeProgram {
  program_id: string;
  course_name: string;
  aliases: string[];
  college_name: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
  ranking_score: number;
  degree: string;
  delivery: string;
  overview: string;
  curriculum_summary: string;
  semester_plan: SemesterPlan[];
  required_papers: string[];
  admission_factors: string[];
  fees: ProgramFees;
  decision_factors: string[];
  sources: ProgramSource[];
  evidence: ProgramEvidence[];
  data_quality_flags: string[];
  last_checked_at: string | null;
  carnegie_classification: string | null;
  rankings: RankingLink[];
  licensed_rankings: LicensedRanking[];
}

export interface RankedProgram {
  program: CollegeProgram;
  distance_miles: number | null;
  match_reason: string;
}

export interface ProgramTier {
  tier: 'nearby' | 'home_state' | 'nearby_home_states' | 'best_usa';
  title: string;
  programs: RankedProgram[];
}

export interface CourseSearchResponse {
  request_id: string;
  query: string;
  location_used: string;
  tiers: ProgramTier[];
  guidance: string[];
}

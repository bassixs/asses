export interface Center {
  id: number;
  name: string;
  created_at?: string;
  participants?: number;
  exercises?: number;
  processed?: number;
  created_by?: string | null;
}

export interface WebUser {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at?: string | null;
  last_login?: string | null;
  is_self?: boolean;
  password?: string; // returned once, only right after create / reset
}

export interface Me {
  authenticated: boolean;
  username: string;
  is_admin: boolean;
}

export interface Participant {
  id: number;
  code: string;
  center_id: number;
  has_report?: boolean;
  processed_count?: number;
}

export interface Exercise {
  id: number;
  name: string;
  participant_id: number;
  center_id: number;
  has_instructions: boolean;
  template_id?: number | null;
  notebook_indicator_count?: number | null;
  has_result?: boolean;
}

export interface Understanding {
  summary: string;
  format: string;
  participant_role: string;
  facilitator_role: string;
  expected_situations: string[];
  competencies_covered: string[];
  not_observable: string[];
  nz_guidance: string;
  gaps: string[];
  understood: boolean;
  understood_reason: string;
  source?: string;
}

export interface TemplateMaterial {
  id: number;
  file_name: string;
  chars: number | null;
}

export interface ExerciseTemplate {
  id: number;
  name: string;
  description: string | null;
  status: "draft" | "ready";
  understood: boolean;
  is_usable: boolean;
  has_notebook: boolean;
  notebook_file_name: string | null;
  notebook_indicator_count: number | null;
  material_count: number;
  instructions_chars: number;
  instructions_limit: number;
  instructions_truncated: boolean;
  checked_at: string | null;
  activated_at: string | null;
  understanding?: Understanding | null;
  materials?: TemplateMaterial[];
}

export interface LevelInfo {
  level: number;
}

export interface ExerciseStatus {
  stage: string;
  message: string;
  has_result: boolean;
  levels: Record<string, LevelInfo>;
  indicator_count: number | null;
  assessed_at?: string | null;
  source?: "audio" | "manual" | null;
  counts?: { "+": number; "-": number; "НЗ": number } | null;
  summary?: string | null;
}

export interface Overview {
  counts: {
    centers: number;
    participants: number;
    exercises: number;
    processed: number;
    reports: number;
  };
  level_max: number;
  avg_level: number;
  measurements: number;
  avg_by_competence: { name: string; avg: number; count: number }[];
  level_bands: { name: string; count: number }[];
  by_center: {
    id: number;
    name: string;
    participants: number;
    exercises: number;
    processed: number;
    avg_level: number | null;
  }[];
  catalog: { total: number; usable: number; needs_notebook: number; draft: number };
}

export interface Storage {
  total_files: number;
  total_size: number;
  orphan_count: number;
  orphan_size: number;
  skipped_recent: number;
  min_age_minutes: number;
  orphans: { name: string; size: number; age_hours: number }[];
}

export interface Center {
  id: number;
  name: string;
  created_at?: string;
}

export interface Participant {
  id: number;
  code: string;
  center_id: number;
}

export interface Exercise {
  id: number;
  name: string;
  participant_id: number;
  center_id: number;
  has_instructions: boolean;
  template_id?: number | null;
  notebook_indicator_count?: number | null;
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
}

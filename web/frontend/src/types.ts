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

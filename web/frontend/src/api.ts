import { demoApi, IS_DEMO } from "./demo";
import type {
  Center,
  Exercise,
  ExerciseStatus,
  ExerciseTemplate,
  Me,
  Overview,
  Participant,
  Storage,
  WebUser,
} from "./types";

export { IS_DEMO };

const BASE = "/api";

/** Error carrying the HTTP status, so callers can tell "not signed in" from a real failure. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore non-JSON errors */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

function jsonPost<T>(path: string, body: unknown): Promise<T> {
  return req<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return req<T>(path, { method: "POST", body: form });
}

/** Trigger a browser download from a GET or POST endpoint that returns a file. */
async function downloadFile(path: string, method: "GET" | "POST" = "GET"): Promise<void> {
  const res = await fetch(BASE + path, { method });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const name = match ? match[1] : "download";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const realApi = {
  login: (username: string, password: string) =>
    jsonPost<{ ok: boolean; username: string; is_admin: boolean }>("/auth/login", { username, password }),
  logout: () => jsonPost<{ ok: boolean }>("/auth/logout", {}),
  me: () => req<Me>("/auth/me"),

  // ---- users (admin) ----
  listUsers: () => req<WebUser[]>("/users"),
  createUser: (username: string, isAdmin: boolean) =>
    jsonPost<WebUser>("/users", { username, is_admin: isAdmin }),
  resetUserPassword: (id: number) => jsonPost<WebUser>(`/users/${id}/reset-password`, {}),
  patchUser: (id: number, patch: { is_active?: boolean; is_admin?: boolean }) =>
    req<WebUser>(`/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteUser: (id: number) => req<{ ok: boolean }>(`/users/${id}`, { method: "DELETE" }),
  changeOwnPassword: () => jsonPost<{ ok: boolean; password: string }>("/users/me/password", {}),

  getOverview: () => req<Overview>("/overview"),

  getStorage: () => req<Storage>("/storage"),
  cleanupStorage: () =>
    jsonPost<{ ok: boolean; deleted: number; freed: number }>("/storage/cleanup", {}),

  listCenters: () => req<Center[]>("/centers"),
  createCenter: (name: string) => jsonPost<Center>("/centers", { name }),
  getCenter: (id: number) => req<Center>(`/centers/${id}`),

  deleteCenter: (id: number) => req<{ ok: boolean }>(`/centers/${id}`, { method: "DELETE" }),
  deleteParticipant: (id: number) => req<{ ok: boolean }>(`/participants/${id}`, { method: "DELETE" }),
  deleteExercise: (id: number) => req<{ ok: boolean }>(`/exercises/${id}`, { method: "DELETE" }),

  listParticipants: (centerId: number) => req<Participant[]>(`/centers/${centerId}/participants`),
  getParticipant: (id: number) => req<Participant>(`/participants/${id}`),
  createParticipant: (centerId: number, code?: string) =>
    jsonPost<Participant>("/participants", { center_id: centerId, code: code || null }),

  listExercises: (participantId: number) => req<Exercise[]>(`/participants/${participantId}/exercises`),
  getExercise: (id: number) => req<Exercise>(`/exercises/${id}`),
  createExercise: (centerId: number, participantId: number, templateId: number) =>
    jsonPost<Exercise>("/exercises", {
      center_id: centerId,
      participant_id: participantId,
      template_id: templateId,
    }),

  // ---- exercise catalog ----
  listTemplates: (usableOnly = false) =>
    req<ExerciseTemplate[]>(`/exercise-templates${usableOnly ? "?usable_only=true" : ""}`),
  getTemplate: (id: number) => req<ExerciseTemplate>(`/exercise-templates/${id}`),
  createTemplate: (name: string, description?: string) =>
    jsonPost<ExerciseTemplate>("/exercise-templates", { name, description: description || null }),
  deleteTemplate: (id: number) =>
    req<{ ok: boolean }>(`/exercise-templates/${id}`, { method: "DELETE" }),
  updateTemplate: (id: number, patch: { name?: string; description?: string }) =>
    req<ExerciseTemplate>(`/exercise-templates/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteMaterial: (id: number, materialId: number) =>
    req<ExerciseTemplate>(`/exercise-templates/${id}/materials/${materialId}`, { method: "DELETE" }),
  uploadTemplateMaterial: (id: number, file: File) =>
    uploadFile<ExerciseTemplate>(`/exercise-templates/${id}/materials`, file),
  uploadTemplateNotebook: (id: number, file: File) =>
    uploadFile<ExerciseTemplate>(`/exercise-templates/${id}/notebook`, file),
  checkTemplate: (id: number) => jsonPost<ExerciseTemplate>(`/exercise-templates/${id}/check`, {}),
  activateTemplate: (id: number) =>
    jsonPost<ExerciseTemplate>(`/exercise-templates/${id}/activate`, {}),
  deactivateTemplate: (id: number) =>
    jsonPost<ExerciseTemplate>(`/exercise-templates/${id}/deactivate`, {}),

  uploadInstructions: (exId: number, file: File) =>
    uploadFile<{ ok: boolean; chars: number }>(`/exercises/${exId}/instructions`, file),
  uploadNotebookTemplate: (exId: number, file: File) =>
    uploadFile<{ ok: boolean; indicators: number }>(`/exercises/${exId}/notebook`, file),
  uploadAudio: (exId: number, file: File) =>
    uploadFile<{ ok: boolean; status: string }>(`/exercises/${exId}/audio`, file),
  uploadFilledNotebook: (exId: number, file: File) =>
    uploadFile<{ ok: boolean; indicators: number; levels: Record<string, { level: number }> }>(
      `/exercises/${exId}/filled-notebook`,
      file,
    ),

  exerciseStatus: (id: number) => req<ExerciseStatus>(`/exercises/${id}/status`),
  downloadFilledNotebook: (id: number) => downloadFile(`/exercises/${id}/filled-notebook`),

  buildReport: (participantId: number) =>
    jsonPost<{ ok: boolean; competencies: Record<string, { avg_level: number }> }>(
      `/participants/${participantId}/report`,
      {},
    ),
  downloadReport: (participantId: number, fmt: "docx" | "pptx") =>
    downloadFile(`/participants/${participantId}/report/file?fmt=${fmt}`),
  downloadIpr: (participantId: number) => downloadFile(`/participants/${participantId}/ipr`, "POST"),
};

// На GitHub Pages (или с ?demo=1) бэкенда нет — работаем на мок-данных.
export const api: typeof realApi = IS_DEMO ? demoApi : realApi;

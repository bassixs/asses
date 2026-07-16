import { demoApi, IS_DEMO } from "./demo";
import type { Center, Exercise, ExerciseStatus, Overview, Participant } from "./types";

export { IS_DEMO };

const BASE = "/api";

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
    throw new Error(detail);
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
  getOverview: () => req<Overview>("/overview"),

  listCenters: () => req<Center[]>("/centers"),
  createCenter: (name: string) => jsonPost<Center>("/centers", { name }),
  getCenter: (id: number) => req<Center>(`/centers/${id}`),

  listParticipants: (centerId: number) => req<Participant[]>(`/centers/${centerId}/participants`),
  getParticipant: (id: number) => req<Participant>(`/participants/${id}`),
  createParticipant: (centerId: number, code?: string) =>
    jsonPost<Participant>("/participants", { center_id: centerId, code: code || null }),

  listExercises: (participantId: number) => req<Exercise[]>(`/participants/${participantId}/exercises`),
  getExercise: (id: number) => req<Exercise>(`/exercises/${id}`),
  createExercise: (centerId: number, participantId: number, name: string) =>
    jsonPost<Exercise>("/exercises", { center_id: centerId, participant_id: participantId, name }),

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

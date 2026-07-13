import type { Center, Exercise, ExerciseStatus, Participant } from "./types";

/**
 * Демо-режим: включается на GitHub Pages (нет бэкенда) или по ?demo=1.
 * Все данные живут в памяти вкладки, «обработка» имитируется таймером.
 */
const params = new URLSearchParams(window.location.search);
if (params.get("demo") === "1") sessionStorage.setItem("demo", "1");

export const IS_DEMO =
  window.location.hostname.endsWith("github.io") || sessionStorage.getItem("demo") === "1";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---- in-memory store, pre-seeded so the UI looks alive ----
let nextId = 100;
const centers: Center[] = [{ id: 1, name: "Ассессмент-центр «Демо»", created_at: new Date().toISOString() }];
const participants: Participant[] = [
  { id: 1, code: "AC-001", center_id: 1 },
  { id: 2, code: "№2", center_id: 1 },
];
const exercises: Exercise[] = [
  { id: 1, name: "Беседа с сотрудником", participant_id: 1, center_id: 1, has_instructions: true },
  { id: 2, name: "Планирование", participant_id: 1, center_id: 1, has_instructions: false },
];

const doneLevels = {
  "ЭФФЕКТИВНАЯ КОММУНИКАЦИЯ": { level: 1.5 },
  "ЭФФЕКТИВНАЯ ОРГАНИЗАЦИЯ": { level: 2 },
  "ОРИЕНТАЦИЯ НА РЕЗУЛЬТАТ": { level: 1.5 },
  "ГОТОВНОСТЬ К ИЗМЕНЕНИЯМ": { level: 1 },
  САМОРАЗВИТИЕ: { level: 2 },
};

const statuses = new Map<number, ExerciseStatus>();
statuses.set(1, { stage: "done", message: "Готово", has_result: true, levels: doneLevels, indicator_count: 89 });

const idle = (): ExerciseStatus => ({ stage: "idle", message: "", has_result: false, levels: {}, indicator_count: null });

function notFound(what: string): never {
  throw new Error(`${what} не найден (демо)`);
}

export const demoApi = {
  async listCenters() {
    await sleep(250);
    return [...centers];
  },
  async createCenter(name: string) {
    await sleep(300);
    const c: Center = { id: ++nextId, name, created_at: new Date().toISOString() };
    centers.unshift(c);
    return c;
  },
  async getCenter(id: number) {
    await sleep(150);
    return centers.find((c) => c.id === id) ?? notFound("Центр");
  },

  async listParticipants(centerId: number) {
    await sleep(200);
    return participants.filter((p) => p.center_id === centerId);
  },
  async getParticipant(id: number) {
    await sleep(150);
    return participants.find((p) => p.id === id) ?? notFound("Участник");
  },
  async createParticipant(centerId: number, code?: string) {
    await sleep(300);
    const id = ++nextId;
    const p: Participant = { id, code: code || `№${id}`, center_id: centerId };
    participants.push(p);
    return p;
  },

  async listExercises(participantId: number) {
    await sleep(200);
    return exercises.filter((e) => e.participant_id === participantId);
  },
  async getExercise(id: number) {
    await sleep(150);
    return exercises.find((e) => e.id === id) ?? notFound("Упражнение");
  },
  async createExercise(centerId: number, participantId: number, name: string) {
    await sleep(300);
    const e: Exercise = { id: ++nextId, name, participant_id: participantId, center_id: centerId, has_instructions: false };
    exercises.push(e);
    return e;
  },

  async uploadInstructions(exId: number, _file: File) {
    await sleep(700);
    const e = exercises.find((x) => x.id === exId);
    if (e) e.has_instructions = true;
    return { ok: true, chars: 8412 };
  },
  async uploadNotebookTemplate(_exId: number, _file: File) {
    await sleep(700);
    return { ok: true, indicators: 89 };
  },
  async uploadAudio(exId: number, _file: File) {
    statuses.set(exId, { stage: "processing", message: "Расшифровка и анализ…", has_result: false, levels: {}, indicator_count: null });
    // имитация конвейера: через несколько секунд «готово»
    setTimeout(() => {
      statuses.set(exId, { stage: "done", message: "Готово", has_result: true, levels: doneLevels, indicator_count: 89 });
    }, 6000);
    await sleep(600);
    return { ok: true, status: "processing" };
  },
  async uploadFilledNotebook(exId: number, _file: File) {
    await sleep(900);
    statuses.set(exId, { stage: "done", message: "Готово", has_result: true, levels: doneLevels, indicator_count: 89 });
    return { ok: true, indicators: 89, levels: doneLevels };
  },

  async exerciseStatus(id: number) {
    await sleep(120);
    return statuses.get(id) ?? idle();
  },
  async downloadFilledNotebook(_id: number): Promise<void> {
    throw new Error("Демо-режим: скачивание файлов недоступно — это витрина интерфейса без бэкенда.");
  },

  async buildReport(_participantId: number) {
    await sleep(1500);
    return {
      ok: true,
      competencies: Object.fromEntries(Object.entries(doneLevels).map(([k, v]) => [k, { avg_level: v.level }])),
    };
  },
  async downloadReport(_participantId: number, _fmt: "docx" | "pptx"): Promise<void> {
    throw new Error("Демо-режим: скачивание файлов недоступно — это витрина интерфейса без бэкенда.");
  },
  async downloadIpr(_participantId: number): Promise<void> {
    throw new Error("Демо-режим: скачивание файлов недоступно — это витрина интерфейса без бэкенда.");
  },
};

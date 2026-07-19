import type {
  Center,
  Exercise,
  ExerciseStatus,
  ExerciseTemplate,
  Overview,
  Participant,
  Understanding,
} from "./types";

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
const centers: Center[] = [
  {
    id: 1,
    name: "Ассессмент-центр «Демо»",
    created_at: new Date().toISOString(),
    participants: 8,
    exercises: 21,
    processed: 17,
  },
  {
    id: 2,
    name: "Резерв руководителей, июль",
    created_at: new Date(Date.now() - 86400000 * 12).toISOString(),
    participants: 14,
    exercises: 34,
    processed: 34,
  },
  {
    id: 3,
    name: "Отбор в кадровый резерв",
    created_at: new Date(Date.now() - 86400000 * 3).toISOString(),
    participants: 5,
    exercises: 9,
    processed: 2,
  },
];
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

const demoOverview: Overview = {
  counts: { centers: 3, participants: 24, exercises: 61, processed: 52, reports: 19 },
  level_max: 3,
  avg_level: 1.9,
  measurements: 260,
  avg_by_competence: [
    { name: "ЭФФЕКТИВНАЯ ОРГАНИЗАЦИЯ", avg: 2.4, count: 52 },
    { name: "ОРИЕНТАЦИЯ НА РЕЗУЛЬТАТ", avg: 2.1, count: 52 },
    { name: "САМОРАЗВИТИЕ", avg: 1.9, count: 52 },
    { name: "ЭФФЕКТИВНАЯ КОММУНИКАЦИЯ", avg: 1.7, count: 52 },
    { name: "ГОТОВНОСТЬ К ИЗМЕНЕНИЯМ", avg: 1.3, count: 52 },
  ],
  level_bands: [
    { name: "Не проявлена", count: 14 },
    { name: "Ниже нормы", count: 63 },
    { name: "Норма", count: 128 },
    { name: "Выше нормы", count: 55 },
  ],
};

const demoUnderstanding: Understanding = {
  summary:
    "Оцениваемый участник играет недавно назначенного руководителя филиала и проводит встречу с подчинённой: ставит задачу, обсуждает сроки и разбирает возражения.",
  format: "индивидуальное",
  participant_role: "Руководитель филиала, проводящий беседу с сотрудником",
  facilitator_role: "Ролевой игрок — подчинённая Марина, мягко сопротивляется задаче",
  expected_situations: [
    "Постановка задачи с неочевидными сроками",
    "Возражение сотрудника и необходимость аргументации",
    "Договорённость о контрольных точках",
  ],
  competencies_covered: [
    "ЭФФЕКТИВНАЯ КОММУНИКАЦИЯ",
    "ЭФФЕКТИВНАЯ ОРГАНИЗАЦИЯ",
    "ОРИЕНТАЦИЯ НА РЕЗУЛЬТАТ",
  ],
  not_observable: ["Индикаторы про публичные выступления — упражнение их не создаёт"],
  nz_guidance:
    "«НЗ» ставим, если ситуация для индикатора не возникла: например, конфликт не был спровоцирован ролевым игроком.",
  gaps: [],
  understood: true,
  understood_reason:
    "Материалов достаточно: понятны роли, сценарий встречи и какие компетенции замеряются блокнотом.",
};

const templates: ExerciseTemplate[] = [
  {
    id: 1,
    name: "Беседа с сотрудником",
    description: "Встроенное упражнение из библиотеки системы.",
    status: "ready",
    understood: true,
    is_usable: true,
    has_notebook: true,
    notebook_file_name: "Блокнот_беседа.xlsx",
    notebook_indicator_count: 89,
    material_count: 3,
    instructions_chars: 8412,
    checked_at: new Date().toISOString(),
    activated_at: new Date().toISOString(),
    understanding: demoUnderstanding,
    materials: [
      { id: 1, file_name: "Инструкция ведущего.pdf", chars: 3120 },
      { id: 2, file_name: "Инструкция наблюдателя.pdf", chars: 2890 },
      { id: 3, file_name: "Инструкция участника.docx", chars: 2402 },
    ],
  },
  {
    id: 2,
    name: "Планирование",
    description: "Встроенное упражнение из библиотеки системы.",
    status: "ready",
    understood: true,
    is_usable: false,
    has_notebook: false,
    notebook_file_name: null,
    notebook_indicator_count: null,
    material_count: 1,
    instructions_chars: 4100,
    checked_at: new Date().toISOString(),
    activated_at: new Date().toISOString(),
    understanding: { ...demoUnderstanding, summary: "Аналитическое упражнение на расстановку приоритетов." },
    materials: [{ id: 4, file_name: "Планирование_методичка.pdf", chars: 4100 }],
  },
  {
    id: 3,
    name: "Групповая дискуссия (новое)",
    description: null,
    status: "draft",
    understood: false,
    is_usable: false,
    has_notebook: true,
    notebook_file_name: "Блокнот_группа.xlsx",
    notebook_indicator_count: 77,
    material_count: 1,
    instructions_chars: 1200,
    checked_at: new Date().toISOString(),
    activated_at: null,
    understanding: {
      ...demoUnderstanding,
      understood: false,
      gaps: [
        "Не указано, сколько участников в группе и есть ли назначенный лидер",
        "Нет инструкции наблюдателя — непонятно, за чем именно следить",
      ],
      understood_reason:
        "Из материалов не ясен формат группы и роль наблюдателя — вести оценку без догадок нельзя.",
    },
    materials: [{ id: 5, file_name: "Кейс_филиал.docx", chars: 1200 }],
  },
];

export const demoApi = {
  async listTemplates(usableOnly = false) {
    await sleep(250);
    return usableOnly ? templates.filter((t) => t.is_usable) : [...templates];
  },
  async getTemplate(id: number) {
    await sleep(200);
    return templates.find((t) => t.id === id) ?? notFound("Упражнение");
  },
  async createTemplate(name: string, description?: string) {
    await sleep(300);
    const t: ExerciseTemplate = {
      id: ++nextId,
      name,
      description: description || null,
      status: "draft",
      understood: false,
      is_usable: false,
      has_notebook: false,
      notebook_file_name: null,
      notebook_indicator_count: null,
      material_count: 0,
      instructions_chars: 0,
      checked_at: null,
      activated_at: null,
      understanding: null,
      materials: [],
    };
    templates.unshift(t);
    return t;
  },
  async deleteTemplate(id: number) {
    await sleep(200);
    const i = templates.findIndex((t) => t.id === id);
    if (i >= 0) templates.splice(i, 1);
    return { ok: true };
  },
  async uploadTemplateMaterial(id: number, file: File) {
    await sleep(800);
    const t = templates.find((x) => x.id === id) ?? notFound("Упражнение");
    t.materials = [...(t.materials ?? []), { id: ++nextId, file_name: file.name, chars: 2500 }];
    t.material_count = t.materials.length;
    t.instructions_chars += 2500;
    t.understood = false;
    t.status = "draft";
    t.is_usable = false;
    return t;
  },
  async uploadTemplateNotebook(id: number, file: File) {
    await sleep(800);
    const t = templates.find((x) => x.id === id) ?? notFound("Упражнение");
    t.has_notebook = true;
    t.notebook_file_name = file.name;
    t.notebook_indicator_count = 89;
    t.understood = false;
    t.status = "draft";
    t.is_usable = false;
    return t;
  },
  async checkTemplate(id: number) {
    await sleep(2500);
    const t = templates.find((x) => x.id === id) ?? notFound("Упражнение");
    t.understanding = demoUnderstanding;
    t.understood = true;
    t.checked_at = new Date().toISOString();
    t.status = "draft";
    t.activated_at = null;
    t.is_usable = false;
    return t;
  },
  async activateTemplate(id: number) {
    await sleep(400);
    const t = templates.find((x) => x.id === id) ?? notFound("Упражнение");
    t.status = "ready";
    t.activated_at = new Date().toISOString();
    t.is_usable = t.has_notebook;
    return t;
  },
  async deactivateTemplate(id: number) {
    await sleep(300);
    const t = templates.find((x) => x.id === id) ?? notFound("Упражнение");
    t.status = "draft";
    t.activated_at = null;
    t.is_usable = false;
    return t;
  },

  async getOverview() {
    await sleep(300);
    return demoOverview;
  },

  async listCenters() {
    await sleep(250);
    return [...centers];
  },
  async createCenter(name: string) {
    await sleep(300);
    const c: Center = {
      id: ++nextId,
      name,
      created_at: new Date().toISOString(),
      participants: 0,
      exercises: 0,
      processed: 0,
    };
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
  async createExercise(centerId: number, participantId: number, templateId: number) {
    await sleep(300);
    const t = templates.find((x) => x.id === templateId);
    const e: Exercise = {
      id: ++nextId,
      name: t?.name ?? "Упражнение",
      participant_id: participantId,
      center_id: centerId,
      has_instructions: true,
      template_id: templateId,
      notebook_indicator_count: t?.notebook_indicator_count ?? null,
    };
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

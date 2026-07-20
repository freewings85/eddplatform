import type {
  Case,
  CaseInput,
  Dataset,
  EvalProgram,
  EvalProgramInput,
  SystemProgram,
  SystemProgramInput,
  ImportResult,
  RunDetail,
  RunRecord,
  System,
  TagNode,
  Task,
  TaskInput,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch("/api" + path);
  if (!resp.ok) throw new Error(`${resp.status} ${path}`);
  return (await resp.json()) as T;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch("/api" + path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${path} ${detail}`);
  }
  return resp.status === 204 ? (undefined as T) : ((await resp.json()) as T);
}

export const api = {
  // 系统注册
  systems: () => get<System[]>("/systems"),
  system: (id: string) => get<System>(`/systems/${id}`),
  createSystem: (s: System) => send<System>("POST", "/systems", s),
  updateSystem: (id: string, s: System) => send<System>("PUT", `/systems/${id}`, s),
  deleteSystem: (id: string) => send<void>("DELETE", `/systems/${id}`),

  // 系统程序注册（被评系统的可部署 git 单元）
  systemPrograms: (sysId: string) => get<SystemProgram[]>(`/systems/${sysId}/system-programs`),
  createSystemProgram: (sysId: string, p: SystemProgramInput) =>
    send<SystemProgram>("POST", `/systems/${sysId}/system-programs`, p),
  updateSystemProgram: (sysId: string, pid: string, p: SystemProgramInput) =>
    send<SystemProgram>("PUT", `/systems/${sysId}/system-programs/${pid}`, p),
  deleteSystemProgram: (sysId: string, pid: string) =>
    send<void>("DELETE", `/systems/${sysId}/system-programs/${pid}`),

  // git 解析（分支→最新 commit；commit→校验+反查分支）
  resolveBranch: (gitUrl: string, branch: string) =>
    send<{ branch: string; commit: string }>("POST", "/git/resolve-branch",
      { git_url: gitUrl, branch }),
  resolveCommit: (gitUrl: string, commit: string) =>
    send<{ commit: string; branches: string[] }>("POST", "/git/resolve-commit",
      { git_url: gitUrl, commit }),

  // 评估程序注册
  evalPrograms: (sysId: string) => get<EvalProgram[]>(`/systems/${sysId}/eval-programs`),
  createEvalProgram: (sysId: string, p: EvalProgramInput) =>
    send<EvalProgram>("POST", `/systems/${sysId}/eval-programs`, p),
  updateEvalProgram: (sysId: string, pid: string, p: EvalProgramInput) =>
    send<EvalProgram>("PUT", `/systems/${sysId}/eval-programs/${pid}`, p),
  deleteEvalProgram: (sysId: string, pid: string) =>
    send<void>("DELETE", `/systems/${sysId}/eval-programs/${pid}`),

  // 用例集
  dataset: (id: string) => get<Dataset>(`/systems/${id}/dataset`),
  createCase: (sysId: string, c: CaseInput) =>
    send<Case>("POST", `/systems/${sysId}/cases`, c),
  updateCase: (sysId: string, caseId: string, c: CaseInput) =>
    send<Case>("PUT", `/systems/${sysId}/cases/${caseId}`, c),
  deleteCase: (sysId: string, caseId: string) =>
    send<void>("DELETE", `/systems/${sysId}/cases/${caseId}`),
  exportCases: (sysId: string) => get<Case[]>(`/systems/${sysId}/cases/export`),
  importCases: (sysId: string, cases: Case[], mode: "append" | "replace") =>
    send<ImportResult>("POST", `/systems/${sysId}/cases/import`, { cases, mode }),
  importCasesYaml: (sysId: string, text: string, mode: "append" | "replace") =>
    send<ImportResult>("POST", `/systems/${sysId}/cases/import-yaml`, { text, mode }),

  // 标签管理（分层）
  tags: (sysId: string) => get<TagNode[]>(`/systems/${sysId}/tags`),
  createTag: (sysId: string, name: string, parentId: string | null) =>
    send<TagNode>("POST", `/systems/${sysId}/tags`, { name, parent_id: parentId }),
  renameTag: (sysId: string, tagId: string, name: string) =>
    send<TagNode>("PUT", `/systems/${sysId}/tags/${tagId}`, { name }),
  deleteTag: (sysId: string, tagId: string) =>
    send<void>("DELETE", `/systems/${sysId}/tags/${tagId}`),

  // 评估任务（含前置条件）+ 执行
  tasks: (sysId: string) => get<Task[]>(`/systems/${sysId}/tasks`),
  createTask: (sysId: string, t: TaskInput) =>
    send<Task>("POST", `/systems/${sysId}/tasks`, t),
  updateTask: (sysId: string, tid: string, t: TaskInput) =>
    send<Task>("PUT", `/systems/${sysId}/tasks/${tid}`, t),
  deleteTask: (sysId: string, tid: string) =>
    send<void>("DELETE", `/systems/${sysId}/tasks/${tid}`),
  runTask: (sysId: string, tid: string) =>
    send<RunRecord>("POST", `/systems/${sysId}/tasks/${tid}/run`),

  // 运行记录
  runs: (sysId?: string) =>
    get<RunRecord[]>(`/runs${sysId ? `?system_id=${encodeURIComponent(sysId)}` : ""}`),
  run: (id: string) => get<RunDetail>(`/runs/${id}`),
};

import type {
  Case,
  CaseInput,
  Comparison,
  Dataset,
  Environment,
  Evaluation,
  EvaluatorDef,
  ImportResult,
  RunRecord,
  System,
  SystemVersion,
  TagNode,
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
  systems: () => get<System[]>("/systems"),
  system: (id: string) => get<System>(`/systems/${id}`),
  versions: (id: string) => get<SystemVersion[]>(`/systems/${id}/versions`),
  dataset: (id: string) => get<Dataset>(`/systems/${id}/dataset`),
  evaluators: (id: string) => get<EvaluatorDef[]>(`/systems/${id}/evaluators`),
  environments: () => get<Environment[]>("/environments"),
  runs: () => get<RunRecord[]>("/runs"),
  evaluations: () => get<Evaluation[]>("/evaluations"),
  comparison: () => get<Comparison>("/comparison"),

  // 用例管理
  createCase: (sysId: string, c: CaseInput) =>
    send<Case>("POST", `/systems/${sysId}/cases`, c),
  updateCase: (sysId: string, caseId: string, c: CaseInput) =>
    send<Case>("PUT", `/systems/${sysId}/cases/${caseId}`, c),
  deleteCase: (sysId: string, caseId: string) =>
    send<void>("DELETE", `/systems/${sysId}/cases/${caseId}`),
  exportCases: (sysId: string) => get<Case[]>(`/systems/${sysId}/cases/export`),
  importCases: (sysId: string, cases: Case[], mode: "append" | "replace") =>
    send<ImportResult>("POST", `/systems/${sysId}/cases/import`, { cases, mode }),

  // 标签管理（分层）
  tags: (sysId: string) => get<TagNode[]>(`/systems/${sysId}/tags`),
  createTag: (sysId: string, name: string, parentId: string | null) =>
    send<TagNode>("POST", `/systems/${sysId}/tags`, { name, parent_id: parentId }),
  renameTag: (sysId: string, tagId: string, name: string) =>
    send<TagNode>("PUT", `/systems/${sysId}/tags/${tagId}`, { name }),
  deleteTag: (sysId: string, tagId: string) =>
    send<void>("DELETE", `/systems/${sysId}/tags/${tagId}`),
};

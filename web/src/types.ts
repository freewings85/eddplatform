// 领域类型（镜像 src/eddplatform/domain/models.py）

export interface Module {
  name: string;
  git_url: string;
  branch: string;
  image: string;
  prod_tag?: string | null;
  owner?: string | null;
}

export interface System {
  id: string;
  name: string;
  owner?: string | null;
  description?: string | null;
  modules?: Module[];
  prod_version?: string | null;
}

export interface EvalProgram {
  id: string;
  system_id: string;
  name: string;
  git_url: string;
  ref: string; // 部署用的 git ref（分支/tag/sha）
  code: string; // RunCase workflow 名 = task queue
  owner?: string | null;
}

export type EvalProgramInput = Omit<EvalProgram, "id" | "system_id"> & {
  id?: string;
  system_id?: string;
};

export type PreconditionKind = "start_system" | "start_eval_program" | "custom_script";

export interface Precondition {
  kind: PreconditionKind;
  name?: string | null;
  git_url?: string | null;
  ref?: string | null; // 选定的版本
  script?: string | null;
}

export interface Task {
  id: string;
  name: string;
  system_id: string;
  dataset_name?: string | null;
  preconditions: Precondition[];
  eval_program_id?: string | null;
  eval_target?: string | null;
}

export type TaskInput = Omit<Task, "id"> & { id?: string };

export interface CaseTrace {
  ref: string;
  url?: string | null;
  note?: string | null;
}

export interface TagNode {
  id: string;
  name: string;
  parent_id?: string | null;
  path: string; // 完整路径，如 业务/报价
}

export interface Case {
  id: string;
  name: string;
  description?: string | null;
  inputs: Record<string, unknown> | string;
  expected_output?: Record<string, unknown> | string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  case_version: string;
  applicable_versions: string[];
  trace?: CaseTrace | null;
  author?: string | null;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 新增/编辑用例的表单负载（id 由服务端生成，时间戳自动维护）。 */
export type CaseInput = Omit<Case, "id" | "created_at" | "updated_at"> & {
  id?: string;
};

export interface ImportResult {
  added: number;
  updated: number;
  total: number;
}

export interface Dataset {
  name: string;
  system_id: string;
  cases: Case[];
  evaluator_names: string[];
}

export interface Outcome {
  kind: string;
  name: string;
  status: string;
  ref?: string | null;
  images?: Record<string, string>;
  detail?: string;
}

export interface RunRecord {
  id: string;
  system_id: string;
  task_id: string;
  task_name: string;
  status: "running" | "succeeded" | "failed";
  workflow_id: string;
  namespace: string;
  versions: Record<string, string>;
  outcomes: Outcome[];
  detail: string;
  created_at?: string | null;
  finished_at?: string | null;
}

export interface CaseRunResult {
  case_id: string;
  status: string; // passed | failed | error
  scores: Record<string, number>;
  metrics: Record<string, number>;
  detail: string;
  trace_url?: string | null;
}

export type RunDetail = RunRecord & { case_results: CaseRunResult[] };

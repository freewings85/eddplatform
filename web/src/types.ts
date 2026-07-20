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
  cases_git_url?: string | null; // 用例仓库（git 管版本）
  cases_branch?: string; // 用例仓分支
  modules?: Module[];
  prod_version?: string | null;
}

export interface SystemProgram {
  id: string;
  system_id: string;
  name: string;
  git_url: string;
  path: string; // 仓库内单元目录
  owner?: string | null;
}

export type SystemProgramInput = Omit<SystemProgram, "id" | "system_id"> & {
  id?: string;
  system_id?: string;
};

export interface EvalProgram {
  id: string;
  system_id: string;
  name: string;
  git_url: string;
  path: string; // 仓库内单元目录（可与被评系统同仓不同目录）
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
  program_id?: string | null; // 引用的 系统程序/评估程序 注册项
  git_url?: string | null; // 固化：保存任务时从注册项复制
  path?: string | null; // 固化：仓库内单元目录（null = 根）
  branch?: string | null; // 固化的分支名（用户可见）
  commit?: string | null; // 固化的 commit sha（部署用它，钉死可复现）
  script?: string | null;
}

export interface Task {
  id: string;
  name: string;
  system_id: string;
  dataset_name?: string | null;
  preconditions: Precondition[];
  dataset_id?: string | null; // 选定的用例库；null = 不跑用例
  case_ids?: string[] | null; // 用例清单：null/缺省 = 全部用例（动态跟随所选库）
  eval_target?: string | null;
}

export type TaskInput = Omit<Task, "id"> & { id?: string };

export interface CaseTrace {
  ref: string;
  url?: string | null;
  note?: string | null;
  data?: Record<string, unknown> | null; // 归档的完整 trace JSON
  archived_at?: string | null;
}

export interface GlobalSettings {
  langfuse_host?: string | null;
  langfuse_public_key?: string | null;
  langfuse_secret_key?: string | null;
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

export interface DatasetInfo {
  id: string;
  system_id: string;
  name: string;
  description?: string | null;
  path?: string | null; // 用例仓里对应的文件夹
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

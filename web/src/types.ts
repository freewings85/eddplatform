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
  env?: string | null; // 部署配置默认值（.env.eval 内容）
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
  env?: string | null; // 部署配置默认值（.env.eval 内容）
  owner?: string | null;
}

export type EvalProgramInput = Omit<EvalProgram, "id" | "system_id"> & {
  id?: string;
  system_id?: string;
};

export interface InfraProgram {
  id: string;
  system_id: string;
  name: string;
  git_url: string; // 独立的组件仓库
  path: string; // 组件集合目录（子文件夹=组件）
  owner?: string | null;
}

export type InfraProgramInput = Omit<InfraProgram, "id" | "system_id"> & {
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
  env?: string | null; // 固化：部署配置（.env.eval 内容，KEY=VALUE 每行）
}

export interface TaskCaseSet {
  dataset_id: string;
  case_ids?: string[] | null; // null = 全部用例（动态跟随用例库）
}

export interface Task {
  id: string;
  name: string;
  system_id: string;
  dataset_name?: string | null;
  preconditions: Precondition[];
  case_sets?: TaskCaseSet[]; // 用例分组（可多个用例库）；非空时优先于下两个旧字段
  dataset_id?: string | null; // 旧单库格式：选定的用例库；null = 不跑用例
  case_ids?: string[] | null; // 旧单库格式：null/缺省 = 全部用例（动态跟随所选库）
  eval_target?: string | null;
  destroy_after?: boolean; // 运行结束后销毁 k8s 资源（namespace）
  runs_per_case?: number; // 每用例执行次数（>1 = 稳定性口径，全过才算过 + pass_rate）
  case_concurrency?: number; // 同一任务内用例并发数（1=串行，默认 4）
  hidden?: boolean; // 软删除：隐藏任务（其运行记录随之隐藏）
  created_at?: string | null;
  updated_at?: string | null;
}

export type TaskInput = Omit<Task, "id"> & { id?: string };

export interface CaseTrace {
  ref?: string | null; // trace id（从 URL 解析，用户不直接填）
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
  id: string; // 内部 id（= 创建时的 name），用户不直接管理
  name: string; // 与评估代码里 case 一一对应的机器名（如 guide_platform_intro）
  description?: string | null;
  tags: string[];
  trace?: CaseTrace | null;
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
  workflow?: string | null; // 评这批用例的 RunCase workflow 名（与评估程序代码里注册的一致）
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
  case_stats?: Record<string, number>;
  detail: string;
  hidden?: boolean; // 软删除：隐藏该运行记录
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
  report?: string; // pydantic-evals 原生报告表（文本渲染）
  program?: string; // 处理本用例的评估程序（workflow 名）
  dataset?: string; // 所属用例集 name（多用例库任务区分来源）
  attempts?: number; // 实际执行次数（任务「每用例执行次数」）
  passed_attempts?: number; // 通过次数（attempts>1 时显示 n/N）
}

export type RunDetail = RunRecord & { case_results: CaseRunResult[] };

export interface RunLogLine {
  id: number;
  ts: string;
  line: string;
}

export interface RunLogPage {
  lines: RunLogLine[];
  last_id: number;
}

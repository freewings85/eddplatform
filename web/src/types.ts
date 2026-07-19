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
  modules: Module[];
  prod_version?: string | null;
}

export interface SystemVersion {
  id: string;
  system_id: string;
  label: string;
  module_pins: Record<string, string>;
  status: string;
  note?: string | null;
}

export interface EvalProgram {
  id: string;
  system_id: string;
  name: string;
  git_url: string;
  branch: string;
  image: string;
  owner?: string | null;
  versions: string[];
  prod_tag?: string | null;
}

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
  evaluator_names: string[];
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

export interface EvaluatorDef {
  name: string;
  kind: string;
  builtin_type?: string | null;
  input_field: string;
  output_type: string;
  threshold?: number | null;
  case_refs: string[];
}

export interface Environment {
  id: string;
  name: string;
  config_name: string;
  version_label: string;
  status: string;
  ttl_hours_left?: number | null;
  purpose?: string | null;
}

export interface RunRecord {
  id: string;
  type: string;
  system_id: string;
  version_label: string;
  status: string;
  duration_s?: number | null;
  eval_id?: string | null;
}

export interface EvalResult {
  pass_rate: number;
  metrics: Record<string, number>;
}

export interface Evaluation {
  id: string;
  name: string;
  version_label: string;
  dataset_name: string;
  status: string;
  run_id?: string | null;
  result?: EvalResult | null;
}

export interface MetricDelta {
  metric: string;
  baseline: number;
  candidate: number;
}

export interface Comparison {
  baseline_eval_id: string;
  candidate_eval_id: string;
  applicable_cases: number;
  improved: number;
  regressed: number;
  unchanged: number;
  metrics: MetricDelta[];
}

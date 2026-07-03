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

export interface Case {
  id: string;
  name: string;
  case_version: string;
  applicable_versions: string[];
  evaluator_names: string[];
  enabled: boolean;
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

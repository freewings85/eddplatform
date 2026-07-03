import type {
  Comparison,
  Dataset,
  Environment,
  Evaluation,
  EvaluatorDef,
  RunRecord,
  System,
  SystemVersion,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch("/api" + path);
  if (!resp.ok) throw new Error(`${resp.status} ${path}`);
  return (await resp.json()) as T;
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
};

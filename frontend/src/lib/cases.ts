/**
 * The farmer's crop cases: a diagnosed problem and its treatment plan as dated
 * steps (src/meta_hackathon/cases.py). The agent starts and updates them with
 * tools; the tracker pane reads them from the tool results and from /v1/cases.
 */
import { API_HEADERS, API_URL, PHONE_HEADER } from "./config";

export type StepStatus = "todo" | "done" | "attention" | "skipped";
export type Outcome = "better" | "same" | "worse";
export type Stage = "in_treatment" | "escalated" | "resolved" | "abandoned";

export type PlanStep = {
  id: string;
  title: string;
  /** action: something the farmer does; check: look at the plants and report. */
  kind: "action" | "check";
  details: string;
  safety_note: string;
  /** YYYY-MM-DD. */
  due: string | null;
  status: StepStatus;
  outcome: Outcome | null;
  note: string;
  /** Cultivation plans: the phase it belongs to ("" otherwise). */
  phase: string;
  /** Days from the plan's start_date, or null. */
  day: number | null;
  /** Where a dose or timing comes from ("" if none). */
  source: string;
};

/** treatment: a crop problem and its treatment. cultivation: growing something, start to harvest. */
export type PlanType = "treatment" | "cultivation";

export type CropCase = {
  id: string;
  crop: string;
  problem: string;
  plot: string;
  plan_type: PlanType;
  /** Treatment: the diagnosis. Cultivation: the goal. */
  diagnosis: string;
  confidence: "high" | "medium" | "low";
  /** Cultivation plans: day 0 (YYYY-MM-DD), and what it is ("চারা রোপণ"). */
  start_date: string | null;
  anchor_label: string;
  stage: Stage;
  started_on: string;
  end_date: string | null;
  next_step: string;
  warning_signs: string[];
  steps: PlanStep[];
  photos: { url: string; caption: string; at: string }[];
  /** Measured from photos, oldest first: lesion = % of the leaf, pests = insects counted. change is against
   * the one before of the same metric (null on the first). Absent on cases saved in older chat messages. */
  measurements?: { id: string; url: string; metric: "lesion" | "pests"; value: number; label: string; at: string; step_id: string | null; change: Outcome | null }[];
  progress: { total: number; done: number; attention: number };
  /** Who did what, newest last (the last 20). */
  activity: { at: string; actor: "agent" | "farmer"; text: string }[];
  updated_at: string;
};

/** Tools whose result carries a case as the ToolMessage artifact. */
export const CASE_TOOLS = new Set(["start_crop_case", "start_cultivation_plan", "update_crop_case", "get_crop_case"]);

export const isCase = (value: unknown): value is CropCase =>
  !!value && typeof value === "object" && typeof (value as CropCase).id === "string" && Array.isArray((value as CropCase).steps);

async function api<T>(phone: string, path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/v1/cases${path}`, {
    ...init,
    headers: { ...API_HEADERS, ...init.headers, [PHONE_HEADER]: phone, ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // not JSON
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export async function listCases(phone: string): Promise<CropCase[]> {
  return (await api<{ cases: CropCase[] }>(phone, "")).cases;
}

/** Tick a step off, skip it, or move it ("" clears the date). */
export function updateStep(phone: string, caseId: string, stepId: string, patch: { status?: StepStatus; due?: string }) {
  return api<CropCase>(phone, `/${caseId}/steps/${stepId}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function updateCase(phone: string, caseId: string, patch: { stage?: Stage; end_date?: string; start_date?: string }) {
  return api<CropCase>(phone, `/${caseId}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function deleteCase(phone: string, caseId: string) {
  return api<{ deleted: string }>(phone, `/${caseId}`, { method: "DELETE" });
}

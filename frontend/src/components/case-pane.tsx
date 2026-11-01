"use client";

// The plan pane: a timeline of every step on the day it is due
// (src/meta_hackathon/cases.py). A treatment plan runs from today to the last
// check; a cultivation plan from land preparation to harvest, its steps counted
// from day 0 (transplanting, sowing, spawning) and grouped into phases.
// KrishiBondhu plans the dates; the farmer can tick actions off, move or skip a
// step, report how the plants look at a check (KrishiBondhu then records it and
// adjusts the plan), send a photo, or ask about any step.

import {
  ArrowRight,
  Bot,
  CalendarDays,
  Camera,
  CircleMinus,
  Eye,
  MessageCircle,
  BookOpen,
  ShieldAlert,
  SprayCan,
  SquareCheck,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  User,
  Minus,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { IconTile } from "@/components/icon-tile";
import { bnDigits } from "@/lib/bn";
import type { CropCase, Outcome, PlanStep, Stage, StepStatus } from "@/lib/cases";

export const STAGE_LABELS: Record<Stage, string> = {
  in_treatment: "চিকিৎসা চলছে",
  escalated: "অফিসারের কাছে",
  resolved: "সেরে গেছে",
  abandoned: "বন্ধ",
};

const CULTIVATION_STAGE_LABELS: Record<Stage, string> = {
  in_treatment: "চলছে",
  escalated: "সমস্যা দেখা দিয়েছে",
  resolved: "শেষ হয়েছে",
  abandoned: "বন্ধ",
};

export const stageLabel = (c: CropCase) =>
  (c.plan_type === "cultivation" ? CULTIVATION_STAGE_LABELS : STAGE_LABELS)[c.stage];

/** "চারা রোপণের ১৫ দিন পর", "চারা রোপণের ২৫ দিন আগে", "চারা রোপণের দিন". */
function anchorDay(label: string, day: number) {
  // Bangla possessive: "রাখা" → "রাখার", "রোপণ" → "রোপণের".
  const of = label ? `${label}${/[\u09BE-\u09CC]$/.test(label) ? "র" : "ের"}` : "শুরুর";
  if (day === 0) return `${of} দিন`;
  return `${of} ${bnDigits(Math.abs(day))} দিন ${day > 0 ? "পর" : "আগে"}`;
}

const STATUS_LABELS: Record<StepStatus, string> = {
  todo: "বাকি",
  done: "সম্পন্ন",
  attention: "নজর দিন",
  skipped: "বাদ",
};

export const OUTCOME_LABELS: Record<Outcome, string> = {
  better: "ভালো হচ্ছে",
  same: "একই রকম",
  worse: "খারাপ হচ্ছে",
};

const CONFIDENCE_LABELS: Record<CropCase["confidence"], string> = { high: "বেশি", medium: "মাঝারি", low: "কম" };

const NODE_ICONS: Record<StepStatus, string> = { todo: "", done: "✓", attention: "!", skipped: "–" };

// ---------------------------------------------------------------------------
// Dates: YYYY-MM-DD strings, compared as local calendar days.
// ---------------------------------------------------------------------------
const DAY = 86_400_000;

function parseDay(iso?: string | null): Date | null {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

function today() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

const toIso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const daysFrom = (from: Date, to: Date) => Math.round((to.getTime() - from.getTime()) / DAY);

const dayLabel = new Intl.DateTimeFormat("bn-BD", { weekday: "short", day: "numeric", month: "short" });
const longLabel = new Intl.DateTimeFormat("bn-BD", { day: "numeric", month: "long" });
const timeLabel = new Intl.DateTimeFormat("bn-BD", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

const isDone = (s: StepStatus) => s === "done" || s === "skipped";

function relative(days: number, done: boolean) {
  if (days === 0) return "আজ";
  if (done) return days < 0 ? `${bnDigits(-days)} দিন আগে` : `${bnDigits(days)} দিন পর`;
  if (days === 1) return "আগামীকাল";
  if (days < 0) return `${bnDigits(-days)} দিন দেরি`;
  return `${bnDigits(days)} দিন পর`;
}

type Urgency = "done" | "overdue" | "soon" | "later" | "undated";

function urgencyOf(step: PlanStep, now: Date): Urgency {
  if (isDone(step.status)) return "done";
  const due = parseDay(step.due);
  if (!due) return "undated";
  const days = daysFrom(now, due);
  return days < 0 ? "overdue" : days <= 1 ? "soon" : "later";
}

type Filter = "all" | "open" | "done";

type Entry =
  | { kind: "step"; step: PlanStep; date: Date | null }
  | { kind: "today"; date: Date }
  | { kind: "end"; date: Date };

/** Steps by date, with markers for today and the last check; undated steps last. */
function buildEntries(steps: PlanStep[], end: Date | null, now: Date): Entry[] {
  const dated: Entry[] = steps
    .filter((s) => parseDay(s.due))
    .map((step) => ({ kind: "step" as const, step, date: parseDay(step.due)! }));
  const markers: Entry[] = [{ kind: "today", date: now }];
  if (end) markers.push({ kind: "end", date: end });
  // On the same day: today's marker before that day's steps, the end after.
  const rank = (e: Entry) => (e.kind === "today" ? 0 : e.kind === "step" ? 1 : 2);
  const sorted = [...dated, ...markers].sort((a, b) => a.date!.getTime() - b.date!.getTime() || rank(a) - rank(b));
  const undated: Entry[] = steps.filter((s) => !parseDay(s.due)).map((step) => ({ kind: "step", step, date: null }));
  return [...sorted, ...undated];
}

// ---------------------------------------------------------------------------
// Pane
// ---------------------------------------------------------------------------
export type CasePaneProps = {
  crop: CropCase | null;
  cases: CropCase[];
  busy: boolean;
  onSelect: (id: string) => void;
  onClose: () => void;
  /** Send a message about this case; `details` reach the model, not the bubble. */
  onAsk: (text: string, details?: Record<string, string>) => void;
  /** Pick a photo for a check step and send it to KrishiBondhu. */
  onPhoto: (crop: CropCase, step: PlanStep) => void;
  onUpdateStep: (crop: CropCase, step: PlanStep, patch: { status?: StepStatus; due?: string }) => Promise<void>;
  onUpdateCase: (crop: CropCase, patch: { stage?: Stage; end_date?: string; start_date?: string }) => Promise<void>;
  onDelete: (crop: CropCase) => Promise<void>;
};

export function CasePane(props: CasePaneProps) {
  const { crop } = props;
  if (!crop) return null;
  return <Timeline key={crop.id} {...props} crop={crop} />;
}

function Timeline({
  crop,
  cases,
  busy,
  onSelect,
  onClose,
  onAsk,
  onPhoto,
  onUpdateStep,
  onUpdateCase,
  onDelete,
}: CasePaneProps & { crop: CropCase }) {
  const now = today();
  const start = parseDay(crop.started_on) ?? now;
  const end = parseDay(crop.end_date);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [editingEnd, setEditingEnd] = useState(false);
  const [editingStart, setEditingStart] = useState(false);
  const cultivation = crop.plan_type === "cultivation";
  const anchor = parseDay(crop.start_date);
  const endWord = cultivation ? "শেষ ধাপ" : "শেষ চেকআপ";
  const [zoomed, setZoomed] = useState<string | null>(null);
  const entryRefs = useRef(new Map<string, HTMLLIElement>());

  // Open on the next thing to do.
  const nextStep = useMemo(
    () =>
      [...crop.steps]
        .filter((s) => !isDone(s.status))
        .sort((a, b) => (a.due ?? "9999").localeCompare(b.due ?? "9999"))[0],
    [crop.steps],
  );
  const [expanded, setExpanded] = useState<string | null>(nextStep?.id ?? null);

  const run = async (key: string, task: () => Promise<void>) => {
    setWorking(key);
    setError(null);
    try {
      await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(null);
    }
  };

  const reveal = (id: string) => {
    setFilter("all");
    setExpanded(id);
    requestAnimationFrame(() => entryRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  };

  const overdue = crop.steps.filter((s) => urgencyOf(s, now) === "overdue");
  const counts = {
    all: crop.steps.length,
    open: crop.steps.filter((s) => !isDone(s.status)).length,
    done: crop.steps.filter((s) => isDone(s.status)).length,
  };
  const shown = (s: PlanStep) => filter === "all" || (filter === "open" ? !isDone(s.status) : isDone(s.status));
  const entries = buildEntries(crop.steps, end, now).filter((e) => e.kind !== "step" || shown(e.step));

  const { done, total, attention } = crop.progress;
  const percent = total ? Math.round((done / total) * 100) : 0;
  const closed = crop.stage === "resolved" || crop.stage === "abandoned";
  const dayOf = daysFrom(start, now) + 1;
  const planDays = end ? daysFrom(start, end) + 1 : null;
  const daysLeft = end ? daysFrom(now, end) : null;
  const about = { case_id: crop.id };

  return (
    <aside className="pane case-pane" aria-label={cultivation ? "চাষের পরিকল্পনা" : "চিকিৎসার পরিকল্পনা"}>
      <header className="pane-head">
        <div className="pane-title">
          <span className="eyebrow">
            {cultivation ? "চাষের পরিকল্পনা" : "চিকিৎসার পরিকল্পনা"} · {crop.crop}
          </span>
          {cases.length > 1 ? (
            <select value={crop.id} onChange={(e) => onSelect(e.target.value)} aria-label="পরিকল্পনা বাছুন">
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.problem}
                  {c.plot ? ` · ${c.plot}` : ""}
                </option>
              ))}
            </select>
          ) : (
            <strong>
              {crop.problem}
              {crop.plot && <span className="pane-plot"> · {crop.plot}</span>}
            </strong>
          )}
          <div className="pane-pills">
            <span className={`stage stage-${crop.stage}`}>{stageLabel(crop)}</span>
            {!cultivation && (
              <span className={`stage confidence-${crop.confidence}`}>নিশ্চয়তা: {CONFIDENCE_LABELS[crop.confidence]}</span>
            )}
            {anchor &&
              (editingStart ? (
                <input
                  type="date"
                  className="stage anchor-input"
                  defaultValue={crop.start_date ?? ""}
                  autoFocus
                  aria-label={`${crop.anchor_label || "শুরুর"} তারিখ`}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (!value) return;
                    void run("start", async () => {
                      await onUpdateCase(crop, { start_date: value });
                      setEditingStart(false);
                    });
                  }}
                  onBlur={() => setEditingStart(false)}
                />
              ) : (
                <button
                  type="button"
                  className="stage anchor"
                  onClick={() => setEditingStart(true)}
                  title="তারিখ বদলালে সব ধাপ সেই হিসাবে সরে যাবে"
                >
                  <CalendarDays size={11} /> {crop.anchor_label || "শুরু"}: {longLabel.format(anchor)}
                </button>
              ))}
          </div>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="প্যানেল বন্ধ করুন">
          <X size={16} />
        </button>
      </header>

      <div className="pane-body">
        {crop.diagnosis && <p className="cp-diagnosis">{crop.diagnosis}</p>}
        {anchor && <p className="cp-anchor-day">আজ {anchorDay(crop.anchor_label, daysFrom(anchor, now))}</p>}

        <section className="cp-hero">
          <ProgressRing percent={percent} />
          <div className="countdown">
            {editingEnd ? (
              <label className="end-edit">
                <span>{endWord}-এর তারিখ</span>
                <input
                  type="date"
                  defaultValue={crop.end_date ?? ""}
                  min={toIso(now)}
                  autoFocus
                  onChange={(e) => {
                    const value = e.target.value;
                    if (!value) return;
                    void run("end", async () => {
                      await onUpdateCase(crop, { end_date: value });
                      setEditingEnd(false);
                    });
                  }}
                  onBlur={() => setEditingEnd(false)}
                />
              </label>
            ) : (
              <button type="button" className="countdown-btn" onClick={() => setEditingEnd(true)} title={`${endWord}-এর তারিখ বদলান`}>
                {planDays && dayOf >= 1 && dayOf <= planDays ? (
                  <span className="big">
                    {bnDigits(dayOf)}
                    <small> / {bnDigits(planDays)} দিন</small>
                  </span>
                ) : (
                  <span className={daysLeft !== null && daysLeft < 0 ? "big past" : "big"}>
                    {daysLeft !== null && daysLeft < 0 ? "শেষ" : "চলছে"}
                  </span>
                )}
                <span className="sub">
                  {end
                    ? daysLeft! > 0
                      ? `${endWord} ${bnDigits(daysLeft!)} দিন পর · ${longLabel.format(end)}`
                      : daysLeft === 0
                        ? `আজ ${endWord}`
                        : `${endWord} ছিল ${longLabel.format(end)}`
                    : `${endWord}-এর তারিখ দিন`}
                </span>
              </button>
            )}
            <span className="sub">
              {bnDigits(total)}টির মধ্যে {bnDigits(done)}টি ধাপ সম্পন্ন
              {attention ? ` · ${bnDigits(attention)}টিতে নজর দরকার` : ""}
            </span>
          </div>
        </section>

        <Track steps={crop.steps} start={start} end={end} endWord={endWord} now={now} onPick={reveal} />

        {crop.next_step && !closed && (
          <div className="next-step">
            <IconTile icon={ArrowRight} tone="green" />
            <div>
              <span className="label">পরের কাজ</span>
              {crop.next_step}
            </div>
          </div>
        )}
        {overdue.length > 0 && !closed && (
          <div className="overdue-banner">
            <TriangleAlert size={15} />
            <span>{bnDigits(overdue.length)}টি ধাপের সময় পেরিয়ে গেছে।</span>
            <button
              type="button"
              className="link-btn"
              disabled={busy}
              onClick={() => onAsk("আমার পরিকল্পনার কিছু ধাপের সময় পেরিয়ে গেছে। নতুন করে তারিখ ঠিক করে দিন।", about)}
            >
              নতুন তারিখ ঠিক করুন
            </button>
          </div>
        )}
        {crop.warning_signs.length > 0 && !closed && (
          <section className="warning-signs">
            <h3>
              <ShieldAlert size={14} /> এমন দেখলে সাথে সাথে জানান
            </h3>
            <ul>
              {crop.warning_signs.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            <button
              type="button"
              className="btn danger-soft"
              disabled={busy}
              onClick={() => onAsk("আমার ফসলে সতর্ক সংকেতের মতো কিছু দেখছি।", about)}
            >
              এমন কিছু দেখছি
            </button>
          </section>
        )}
        {error && <div className="tracker-error">{error}</div>}

        <div className="tl-filters" role="tablist">
          {(["all", "open", "done"] as const).map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              className={filter === f ? "on" : ""}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "সব" : f === "open" ? "বাকি" : "সম্পন্ন"} <span className="count">{bnDigits(counts[f])}</span>
            </button>
          ))}
        </div>

        <ol className="tl">
          {entries.map((entry, idx) => {
            if (entry.kind !== "step") {
              return (
                <li key={entry.kind} className={`tl-marker ${entry.kind}`}>
                  <span className="tl-date">{dayLabel.format(entry.date)}</span>
                  <span className="tl-rail">
                    <span className="tl-node" />
                  </span>
                  <span className="tl-marker-label">{entry.kind === "today" ? "আজ" : endWord}</span>
                </li>
              );
            }
            const { step, date } = entry;
            const firstUndated = !date && (idx === 0 || entries[idx - 1].kind !== "step" || !!entries[idx - 1].date);
            // A phase header where the phase changes from the step before (markers do not count).
            const prevStep = entries
              .slice(0, idx)
              .reverse()
              .find((e): e is Extract<Entry, { kind: "step" }> => e.kind === "step");
            const phaseStart = !!step.phase && step.phase !== prevStep?.step.phase;
            const urgency = urgencyOf(step, now);
            const open = expanded === step.id;
            const check = step.kind === "check";
            return (
              <li
                key={step.id}
                ref={(el) => {
                  if (el) entryRefs.current.set(step.id, el);
                  else entryRefs.current.delete(step.id);
                }}
                className={`tl-entry ${urgency} status-${step.status}${step.outcome ? ` outcome-${step.outcome}` : ""}${open ? " open" : ""}`}
              >
                {firstUndated && <div className="tl-section">তারিখ ঠিক হয়নি</div>}
                {phaseStart && !firstUndated && <div className="tl-section tl-phase">{step.phase}</div>}
                <div className="tl-row">
                  <span className="tl-date">
                    {date ? (
                      <>
                        {dayLabel.format(date)}
                        <small>{relative(daysFrom(now, date), isDone(step.status))}</small>
                      </>
                    ) : (
                      "—"
                    )}
                  </span>
                  <span className="tl-rail">
                    <span className="tl-node" title={STATUS_LABELS[step.status]}>
                      {NODE_ICONS[step.status]}
                    </span>
                  </span>
                  <div className="tl-card">
                    <button type="button" className="tl-head" aria-expanded={open} onClick={() => setExpanded(open ? null : step.id)}>
                      <span className="tl-title">
                        <IconTile icon={check ? Eye : SprayCan} tone={check ? "cyan" : "green"} size="s" />
                        <strong>{step.title}</strong>
                      </span>
                      <span className={`status-pill ${step.outcome ? `outcome-${step.outcome}` : step.status}`}>
                        {step.outcome ? OUTCOME_LABELS[step.outcome] : STATUS_LABELS[step.status]}
                      </span>
                    </button>
                    {step.note && !open && <p className="item-note">{step.note}</p>}
                    {open && (
                      <div className="tl-body">
                        {step.day !== null && cultivation && (
                          <p className="item-day">{anchorDay(crop.anchor_label, step.day)}</p>
                        )}
                        {step.details && <p className="item-details">{step.details}</p>}
                        {step.safety_note && (
                          <p className="item-safety">
                            <ShieldAlert size={13} /> {step.safety_note}
                          </p>
                        )}
                        {step.note && <p className="item-note">{step.note}</p>}
                        {step.source && (
                          <p className="item-source">
                            <BookOpen size={12} /> উৎস: {step.source}
                          </p>
                        )}
                        {check && step.status !== "skipped" && !closed && (
                          <div className="outcomes" role="group" aria-label={cultivation ? "ফসল এখন কেমন?" : "গাছ এখন কেমন?"}>
                            <span className="outcomes-label">{cultivation ? "ফসল এখন কেমন?" : "গাছ এখন কেমন?"}</span>
                            {(
                              [
                                ["better", TrendingUp],
                                ["same", Minus],
                                ["worse", TrendingDown],
                              ] as const
                            ).map(([outcome, Icon]) => (
                              <button
                                key={outcome}
                                type="button"
                                className={`btn outcome ${outcome}${step.outcome === outcome ? " on" : ""}`}
                                disabled={busy}
                                onClick={() =>
                                  onAsk(`"${step.title}": ${cultivation ? "ফসল" : "গাছ"} ${OUTCOME_LABELS[outcome]}।`, {
                                    ...about,
                                    step_id: step.id,
                                    outcome,
                                  })
                                }
                              >
                                <Icon size={13} />
                                {OUTCOME_LABELS[outcome]}
                              </button>
                            ))}
                          </div>
                        )}
                        <div className="item-actions">
                          {check && step.status !== "skipped" && !closed && (
                            <button type="button" className="btn primary-soft" disabled={busy} onClick={() => onPhoto(crop, step)}>
                              <Camera size={13} />
                              ছবি পাঠান
                            </button>
                          )}
                          {!check && step.status !== "skipped" && (
                            <button
                              type="button"
                              className="btn primary-soft"
                              disabled={!!working}
                              onClick={() =>
                                run(step.id, () => onUpdateStep(crop, step, { status: step.status === "done" ? "todo" : "done" }))
                              }
                            >
                              <SquareCheck size={13} />
                              {step.status === "done" ? "করা হয়নি" : "করেছি"}
                            </button>
                          )}
                          <label className="btn date-btn" title="ধাপটি অন্য দিনে সরান">
                            <CalendarDays size={13} />
                            <input
                              type="date"
                              value={step.due ?? ""}
                              disabled={!!working}
                              onChange={(e) => void run(step.id, () => onUpdateStep(crop, step, { due: e.target.value }))}
                            />
                          </label>
                          <button
                            type="button"
                            className="btn"
                            disabled={!!working}
                            onClick={() =>
                              run(step.id, () =>
                                onUpdateStep(crop, step, { status: step.status === "skipped" ? "todo" : "skipped" }),
                              )
                            }
                          >
                            <CircleMinus size={13} />
                            {step.status === "skipped" ? "আবার রাখুন" : "বাদ দিন"}
                          </button>
                          <button
                            type="button"
                            className="btn"
                            disabled={busy}
                            onClick={() =>
                              onAsk(`"${step.title}" ধাপটি আরেকটু বুঝিয়ে বলুন।`, { ...about, step_id: step.id })
                            }
                          >
                            <MessageCircle size={13} />
                            জিজ্ঞেস করুন
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        {!!crop.measurements?.length && <MeasuredTrend measurements={crop.measurements} />}

        {crop.photos.length > 0 && (
          <section className="cp-photos">
            <h3>ছবিতে অগ্রগতি</h3>
            <div className="cp-photo-grid">
              {crop.photos.map((p) => (
                <figure key={p.url}>
                  <button type="button" onClick={() => setZoomed(p.url)} aria-label="ছবি বড় করে দেখুন">
                    {/* eslint-disable-next-line @next/next/no-img-element -- annotated photos from /media */}
                    <img src={p.url} alt={p.caption || "ফসলের ছবি"} loading="lazy" />
                  </button>
                  <figcaption>
                    {p.caption && <span>{p.caption}</span>}
                    <time dateTime={p.at}>{timeLabel.format(new Date(p.at))}</time>
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
        )}

        <Activity events={crop.activity} />

        <div className="cp-footer">
          {!closed && (
            <button
              type="button"
              className="btn"
              disabled={!!working}
              onClick={() => run("stage", () => onUpdateCase(crop, { stage: "resolved" }))}
            >
              <SquareCheck size={13} />
              {cultivation ? "চাষ শেষ হয়েছে" : "সমস্যা মিটে গেছে"}
            </button>
          )}
          <button
            type="button"
            className="link-btn danger"
            disabled={!!working}
            onClick={() => {
              if (confirm(`"${crop.problem}" পরিকল্পনাটি মুছে ফেলবেন?`)) void run("delete", () => onDelete(crop));
            }}
          >
            পরিকল্পনা মুছুন
          </button>
        </div>
      </div>

      {zoomed && (
        <div className="lightbox" role="dialog" aria-label="ছবি" onClick={() => setZoomed(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element -- annotated photo */}
          <img src={zoomed} alt="ফসলের ছবি" />
        </div>
      )}
    </aside>
  );
}

const MEASURE_WORDS = {
  lesion: { title: "ছবিতে মাপা পাতার দাগ", worse: "দাগ বেড়েছে", better: "মাপে দাগ কমেছে", first: "প্রথম মাপ: পরের ছবিতে একই পাতা দিন" },
  pests: { title: "ছবিতে গোনা পোকা", worse: "পোকা বেড়েছে", better: "ছবিতে পোকা কমেছে", first: "প্রথম গণনা: পরের ছবিও একই দূরত্ব থেকে দিন" },
};

/** What was measured from the photos, first to latest, and what the latest change means. */
function MeasuredTrend({ measurements }: { measurements: NonNullable<CropCase["measurements"]> }) {
  return (
    <>
      {(["pests", "lesion"] as const).map((metric) => {
        const series = measurements.filter((m) => (m.metric ?? "lesion") === metric);
        const latest = series[series.length - 1];
        if (!latest) return null;
        const words = MEASURE_WORDS[metric];
        return (
          <section className="cp-lesions" key={metric}>
            <h3>{metric === "pests" && latest.label ? `ছবিতে গোনা ${latest.label}` : words.title}</h3>
            <p className="cp-lesion-values">
              {series.slice(-4).map((m, i) => (
                <span key={m.id}>
                  {i > 0 && <span aria-hidden="true"> → </span>}
                  <strong>{bnDigits(m.value)}{metric === "lesion" ? "%" : "টি"}</strong>
                </span>
              ))}
            </p>
            {latest.change ? (
              <span className={`status-pill outcome-${latest.change}`}>
                {latest.change === "worse" ? <TrendingDown size={13} /> : null}
                {latest.change === "worse" ? words.worse : latest.change === "better" ? words.better : "তেমন বদল নেই"}
              </span>
            ) : (
              <span className="cp-lesion-hint">{words.first}</span>
            )}
          </section>
        );
      })}
    </>
  );
}

function ProgressRing({ percent }: { percent: number }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  return (
    <div className="ring" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <svg viewBox="0 0 72 72" width="72" height="72">
        <circle cx="36" cy="36" r={r} className="ring-bg" />
        <circle
          cx="36"
          cy="36"
          r={r}
          className="ring-fg"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - percent / 100)}
          transform="rotate(-90 36 36)"
        />
      </svg>
      <span>{bnDigits(percent)}%</span>
    </div>
  );
}

/** Start to the last check on one line, a dot per dated step; a dot opens its step. */
function Track({
  steps,
  start,
  end,
  endWord,
  now,
  onPick,
}: {
  steps: PlanStep[];
  start: Date;
  end: Date | null;
  endWord: string;
  now: Date;
  onPick: (id: string) => void;
}) {
  const dated = steps.filter((s) => parseDay(s.due));
  if (!dated.length && !end) return null;

  const times = [start, now, ...dated.map((s) => parseDay(s.due)!), ...(end ? [end] : [])].map((d) => d.getTime());
  const from = Math.min(...times);
  const to = Math.max(...times, from + 3 * DAY);
  const at = (d: Date) => ((d.getTime() - from) / (to - from)) * 100;

  return (
    <div className="track" aria-label="সময়রেখা">
      <div className="track-line">
        <span className="track-elapsed" style={{ width: `${at(now)}%` }} />
        {dated.map((step) => (
          <button
            key={step.id}
            type="button"
            className={`track-dot ${urgencyOf(step, now)} status-${step.status}${step.outcome ? ` outcome-${step.outcome}` : ""}`}
            style={{ left: `${at(parseDay(step.due)!)}%` }}
            data-label={`${step.title} · ${dayLabel.format(parseDay(step.due)!)}`}
            aria-label={`${step.title}, ${STATUS_LABELS[step.status]}, ${dayLabel.format(parseDay(step.due)!)}`}
            onClick={() => onPick(step.id)}
          />
        ))}
        <span className="track-today" style={{ left: `${at(now)}%` }}>
          <span>আজ</span>
        </span>
        {end && <span className="track-end" style={{ left: `${at(end)}%` }} title={`${endWord} · ${longLabel.format(end)}`} />}
      </div>
    </div>
  );
}

/** Who did what to this plan, newest first: what KrishiBondhu also reads. */
function Activity({ events }: { events: CropCase["activity"] }) {
  const [open, setOpen] = useState(false);
  if (!events.length) return null;
  const shown = [...events].reverse().slice(0, open ? 20 : 4);
  return (
    <section className="cp-activity">
      <h3>যা যা হয়েছে</h3>
      <ol>
        {shown.map((e, i) => (
          <li key={`${e.at}-${i}`} className={e.actor}>
            <span className="who">
              {e.actor === "farmer" ? <User size={12} /> : <Bot size={12} />}
              {e.actor === "farmer" ? "আপনি" : "কৃষিবন্ধু"}
            </span>
            <span className="what">{bnDigits(e.text)}</span>
            <time dateTime={e.at}>{timeLabel.format(new Date(e.at))}</time>
          </li>
        ))}
      </ol>
      {events.length > 4 && (
        <button type="button" className="link-btn" onClick={() => setOpen((o) => !o)}>
          {open ? "কম দেখান" : `সব ${bnDigits(events.length)}টি দেখুন`}
        </button>
      )}
    </section>
  );
}

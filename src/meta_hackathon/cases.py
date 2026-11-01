"""Plans KrishiBondhu tracks with a farmer ("cases"): storage, the rules, and
how a plan is shown to the web UI and to the model (docs/04-case-lifecycle.md).

Two kinds share one timeline of dated steps:

- treatment: one crop problem (rice blast in one plot, aphids on brinjal in
  another) with its treatment, from today to the last check.
- cultivation: growing something, start to harvest (a Boro rice season, oyster
  mushrooms at home, a fertiliser schedule). Steps are counted in days from a
  start date (`start_date`, e.g. the transplanting day; `anchor_label` says
  what it is), so when that date moves every step moves with it; they are
  grouped into phases (জমি তৈরি, সার, সেচ, ফসল কাটা ...).

    {
        "id": "s3",                  # stable within the case
        "title": "ট্রাইসাইক্লাজল স্প্রে করুন",
        "kind": "action",            # action: something to do | check: look at the plants and report
        "details": "১০ লিটার পানিতে ৬ গ্রাম, বিকেলে",
        "safety_note": "মাস্ক ও গ্লাভস পরুন",
        "due": "2026-10-30",         # ISO date, or None
        "status": "todo",            # see Status
        "outcome": None,             # for checks: better | same | worse
        "note": "",                  # KrishiBondhu's comment on how it went
        "phase": "সার প্রয়োগ",        # cultivation plans: the phase it belongs to ("" otherwise)
        "day": 15,                   # days from the plan's start_date (negative = before it), or None
        "source": "BRRI, আধুনিক ধানের চাষ",  # where a dose or timing comes from ("" if none)
    }

Both the agent (tools/cases.py) and the farmer (the pane, api/cases.py) change
a case. Every change reads the row FOR UPDATE and writes it in one transaction, so
neither overwrites the other, and is logged to the case's `activity` -- who did
what, newest last -- so the agent knows what the farmer did in the pane between
messages.

Stored in Postgres with db.py, under row-level security per farmer. Calls
block, so async code runs them with asyncio.to_thread.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from psycopg import Connection
from psycopg.types.json import Jsonb

from meta_hackathon.db import farmer
from meta_hackathon.gallery import media_url
from meta_hackathon.utils.bangla import bn_digits

Kind = Literal["action", "check"]
# todo: not yet. done: done, or a check answered. attention: something went
# wrong (the note says what). skipped: does not apply any more.
Status = Literal["todo", "done", "attention", "skipped"]
Outcome = Literal["better", "same", "worse"]
# For a cultivation plan: in_treatment = under way, escalated = a problem came up,
# resolved = harvested / finished, abandoned = stopped.
Stage = Literal["in_treatment", "escalated", "resolved", "abandoned"]
Confidence = Literal["high", "medium", "low"]
PlanType = Literal["treatment", "cultivation"]
CLOSED_STAGES = {"resolved", "abandoned"}

MAX_OPEN_CASES = 6
MAX_STEPS_BY_TYPE = {"treatment": 20, "cultivation": 40}
MAX_PHOTOS = 12
MAX_ACTIVITY = 40
MAX_TEXT = 300
MAX_TITLE = 120
MAX_MEASUREMENTS = 12
# (smallest absolute change, smallest relative change) that counts as real. The same leaf reframed
# read 13.9-16.4% where it should read 14.5%. An insect count barely moved with light (114 -> 112) but
# follows the framing (half the leaf, 74), so it needs a bigger change.
MEASURE_MIN_CHANGE = {"lesion": (3.0, 0.25), "pests": (10, 0.5)}
AGENT, FARMER = "agent", "farmer"
Actor = Literal["agent", "farmer"]


def _iso_date(value: str | None) -> str | None:
    """A YYYY-MM-DD date, or None for an empty value."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{value!r} is not a date; write it as YYYY-MM-DD") from None


class PlanStepInput(BaseModel):
    """One step of a plan, as the agent writes it."""

    title: str = Field(description='Short Bangla instruction, e.g. "আক্রান্ত পাতা তুলে পুড়িয়ে ফেলুন".')
    kind: Kind = Field(
        default="action",
        description='"action" for something the farmer does; "check" for a follow-up where they look at the plants '
        "(and send a photo) and tell you if it is better, the same or worse.",
    )
    details: str = Field(default="", description="How exactly: dose, mixing, time of day, where. Bangla.")
    safety_note: str = Field(default="", description="PPE, pre-harvest interval, weather to avoid. Bangla. Empty if none.")
    due: str | None = Field(
        default=None, description="YYYY-MM-DD to do it on. In a cultivation plan, give `day` instead."
    )
    day: int | None = Field(
        default=None,
        description="Cultivation plans: days from the plan's start_date (0 = that day, negative = before it, "
        "e.g. -25 for the seedbed when start_date is transplanting). The date is worked out from it.",
    )
    phase: str = Field(default="", description='Cultivation plans: Bangla phase, e.g. "জমি তৈরি", "সার প্রয়োগ", "ফসল কাটা".')
    source: str = Field(
        default="",
        description="Where a dose, amount or timing comes from (organisation and document, or a search result's "
        'title), e.g. "BRRI, আধুনিক ধানের চাষ". Required for any dose; empty for a common-sense step.',
    )

    @field_validator("due")
    @classmethod
    def _due(cls, v):
        return _iso_date(v)

    @field_validator("day")
    @classmethod
    def _day(cls, v):
        if v is not None and not -400 <= v <= 400:
            raise ValueError("day must be within 400 days of the start date")
        return v


class StepChange(BaseModel):
    """A change to one step already in the plan."""

    step_id: str
    status: Status | None = None
    outcome: Outcome | None = Field(default=None, description="For a check: what the farmer reported.")
    note: str | None = Field(default=None, description="What you made of it, in one Bangla sentence. Shown under the step.")
    due: str | None = Field(default=None, description='YYYY-MM-DD; "" removes the date.')

    @field_validator("due")
    @classmethod
    def _due(cls, v):
        # None leaves the date alone; "" clears it.
        return v if v is None else (_iso_date(v) or "")


class PhotoInput(BaseModel):
    url: str = Field(description="An annotated_image_url from segment_image.")
    caption: str = Field(default="", description='Short Bangla caption, e.g. "৩য় দিন: দাগ কমেছে".')


class CaseError(ValueError):
    """A change that cannot be made, in words for the model or the farmer."""


def _clip(value: str | None, limit: int = MAX_TEXT) -> str:
    return " ".join((value or "").split())[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _event(actor: Actor, text: str) -> dict:
    return {"at": _now(), "actor": actor, "text": text}


_BN_MONTHS = ("জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর")


def _bn_date(iso: str) -> str:
    """"২২ ডিসেম্বর" for the activity log (the web UI turns the digits Bangla)."""
    d = date.fromisoformat(iso)
    return f"{d.day} {_BN_MONTHS[d.month - 1]}"


def _due_from(start_date: str | None, day: int | None) -> str | None:
    if start_date is None or day is None:
        return None
    return (date.fromisoformat(start_date) + timedelta(days=day)).isoformat()


def new_steps(inputs: list[PlanStepInput], start: int = 1, start_date: str | None = None) -> list[dict]:
    """Steps as stored. A step with `day` gets its date from start_date (and keeps
    `day`, so a moved start date moves it); one with only `due` keeps that date."""
    return [
        {
            "id": f"s{start + n}",
            "title": _clip(step.title, MAX_TITLE) or "ধাপ",
            "kind": step.kind,
            "details": _clip(step.details),
            "safety_note": _clip(step.safety_note),
            "phase": _clip(step.phase, 40),
            "day": step.day if start_date is not None else None,
            "source": _clip(step.source, 160),
            "due": step.due if step.day is None or start_date is None else _due_from(start_date, step.day),
            "status": "todo",
            "outcome": None,
            "note": "",
        }
        for n, step in enumerate(inputs)
    ]


def _next_step_number(steps: list[dict]) -> int:
    numbers = [int(s["id"][1:]) for s in steps if s.get("id", "").startswith("s") and s["id"][1:].isdigit()]
    return max(numbers, default=0) + 1


def measured_change(metric: str, before: float, after: float) -> Outcome:
    """What a change in a measurement means, beyond measurement noise."""
    diff = after - before
    least, relative = MEASURE_MIN_CHANGE[metric]
    if abs(diff) < least or abs(diff) < before * relative:
        return "same"
    return "worse" if diff > 0 else "better"


def _shown(metric: str, value: float, label: str = "") -> str:
    """A measurement in Bangla: "১৪.৪%" or "জাব পোকা ১১৪টি"."""
    return f"{bn_digits(value)}%" if metric == "lesion" else f"{label or 'পোকা'} {bn_digits(value)}টি"


def progress(steps: list[dict]) -> dict:
    """Counts over the steps still in the plan."""
    live = [s for s in steps if s["status"] != "skipped"]
    return {
        "total": len(live),
        "done": sum(s["status"] == "done" for s in live),
        "attention": sum(s["status"] == "attention" for s in live),
    }


def next_due(steps: list[dict]) -> dict | None:
    """The earliest step still to do."""
    open_steps = [s for s in steps if s["status"] in ("todo", "attention")]
    return min(open_steps, key=lambda s: s.get("due") or "9999", default=None)


_STEP_DEFAULTS = {"phase": "", "day": None, "source": ""}


def normalized(case: dict) -> dict:
    """Plans saved before cultivation plans existed are treatment plans."""
    return {
        "plan_type": "treatment",
        "start_date": None,
        "anchor_label": "",
        **case,
        "steps": [{**_STEP_DEFAULTS, **step} for step in case["steps"]],
        # Before insects were counted, a measurement held only lesion_pct.
        "measurements": [
            {"metric": "lesion", "value": m.get("lesion_pct"), "label": "", **m} for m in case.get("measurements", [])
        ],
    }


def case_view(case: dict) -> dict:
    """A plan as the web UI gets it: in a tool message's artifact and from the API."""
    case = normalized(case)
    return {**case, "progress": progress(case["steps"]), "activity": case["activity"][-20:]}


def case_for_model(view: dict) -> str:
    """The whole plan in a compact form the agent can act on."""
    p = view["progress"]
    cultivation = view["plan_type"] == "cultivation"
    lines = [
        f"case_id: {view['id']} ({'cultivation plan' if cultivation else 'treatment plan'})",
        f"{view['problem']} on {view['crop']}" + (f" ({view['plot']})" if view["plot"] else "")
        + f" -- stage: {view['stage']}" + ("" if cultivation else f", confidence: {view['confidence']}"),
        f"started {view['started_on']}" + (f", plan ends {view['end_date']}" if view["end_date"] else ""),
    ]
    if view["start_date"]:
        lines.append(
            f"start_date (day 0): {view['start_date']} = {view['anchor_label'] or 'start'}; "
            "steps with a day move when start_date changes"
        )
    lines += [
        f"{p['done']} of {p['total']} steps done, {p['attention']} need attention.",
        f"next step shown: {view['next_step'] or '(none)'}",
        "steps:",
    ]
    phase = None
    for s in view["steps"]:
        if s["phase"] and s["phase"] != phase:
            phase = s["phase"]
            lines.append(f"  [{phase}]")
        line = f"- {s['id']} [{s['status']}] {s['title']} ({s['kind']})"
        if s.get("due"):
            line += f" due {s['due']}"
        if s["day"] is not None:
            line += f" (day {s['day']})"
        if s.get("outcome"):
            line += f" -- reported {s['outcome']}"
        if s["note"]:
            line += f" -- note: {s['note']}"
        if s["source"]:
            line += f" -- source: {s['source']}"
        lines.append(line)
    if view["measurements"]:
        for metric, title, unit in (("lesion", "leaf damage measured from photos", "%"), ("pests", "insects counted in photos", "")):
            if series := [m for m in view["measurements"] if m["metric"] == metric]:
                lines.append(
                    f"{title}, oldest first: "
                    + ", ".join(f"{m['value']}{unit} ({m['change'] or 'first'}, {m['at'][:10]})" for m in series)
                )
    if view["photos"]:
        lines.append(f"{len(view['photos'])} photo(s) on file, latest: {view['photos'][-1]['caption'] or '(no caption)'}")
    if recent := view["activity"][-8:]:
        lines.append("recent activity, oldest first:")
        lines += [
            f"- {a['at'][:16].replace('T', ' ')} {'the farmer' if a['actor'] == FARMER else 'you'}: {a['text']}"
            for a in recent
        ]
    return "\n".join(lines)


def summary_line(case: dict) -> str:
    """One line per plan, for the system prompt."""
    case = normalized(case)
    p = progress(case["steps"])
    line = (
        f"- {case['problem']} on {case['crop']} (case_id: {case['id']}, {case['plan_type']}) -- {case['stage']}, "
        f"{p['done']} of {p['total']} steps done" + (f", {p['attention']} need attention" if p["attention"] else "")
    )
    if case["start_date"]:
        line += f", day 0 = {case['start_date']} ({case['anchor_label'] or 'start'})"
    if case["end_date"]:
        line += f", plan ends {case['end_date']}"
    if due := next_due(case["steps"]):
        line += f", next: {due['title']}" + (f" on {due['due']}" if due.get("due") else "")
    return line


# The activity log is shown to the farmer, so it is in Bangla; the model reads it as well.
STATUS_WORDS = {"todo": "বাকি", "done": "সম্পন্ন", "attention": "নজর দরকার", "skipped": "বাদ"}
OUTCOME_WORDS = {"better": "ভালো হচ্ছে", "same": "একই রকম", "worse": "খারাপ হচ্ছে"}
STAGE_WORDS = {"in_treatment": "চিকিৎসা চলছে", "escalated": "অফিসারের কাছে", "resolved": "সেরে গেছে", "abandoned": "বন্ধ"}
CULTIVATION_STAGE_WORDS = {"in_treatment": "চলছে", "escalated": "সমস্যা দেখা দিয়েছে", "resolved": "শেষ হয়েছে", "abandoned": "বন্ধ"}


def _describe(before: dict, after: dict) -> list[str]:
    """What changed on one step, in a few words each."""
    title = f'"{after["title"]}"'
    said = []
    if after.get("outcome") != before.get("outcome") and after.get("outcome"):
        said.append(f"{title}: {OUTCOME_WORDS[after['outcome']]}")
    if after["status"] != before["status"]:
        text = f"{title}: {STATUS_WORDS[after['status']]}"
        if after["status"] == "attention" and after["note"]:
            text += f" ({after['note']})"
        said.append(text)
    if after.get("due") != before.get("due"):
        said.append(f"{title} সরানো হলো {after['due']}" if after.get("due") else f"{title}-এর তারিখ সরানো হলো")
    return said


# ---------------------------------------------------------------------------
# Storage: crop_cases in Postgres, one jsonb document per case, only ever
# touched inside db.farmer(phone), so row-level security limits every query to
# that farmer's cases (sql/schema.sql).
# ---------------------------------------------------------------------------


def list_cases(phone: str, *, include_closed: bool = True) -> list[dict]:
    with farmer(phone) as conn:
        return list_cases_in(conn, include_closed=include_closed)


def list_cases_in(conn: Connection, *, include_closed: bool = True) -> list[dict]:
    """The calling farmer's cases, newest first, in an open db.farmer() transaction."""
    rows = conn.execute("SELECT data FROM crop_cases ORDER BY updated_at DESC").fetchall()
    cases = [r["data"] for r in rows]
    return cases if include_closed else [c for c in cases if c["stage"] not in CLOSED_STAGES]


def get_case(phone: str, case_id: str) -> dict | None:
    with farmer(phone) as conn:
        row = conn.execute("SELECT data FROM crop_cases WHERE id = %s AND phone = %s", (case_id, phone)).fetchone()
    return row["data"] if row else None


def _attach_measurement(conn: Connection, phone: str, case: dict, measurement_id: str, step_id: str | None) -> list[str]:
    """File what segment_image measured on a photo, compare it with the last reading of
    the same kind, and log it.

    A rise beyond noise is evidence enough to act on: the check is marked worse and the
    case escalates, whatever was reported, since a false alarm costs one phone call. A fall
    changes nothing by itself, since a missed lesion, different light or a wider photo can
    look like healing; the agent has to look at the photo and decide. A first reading of
    zero is not kept: there is nothing to compare it with, and it says nothing about a
    problem this measure cannot see. Returns the activity lines."""
    name = f"{measurement_id}.jpg"
    row = conn.execute("SELECT measurement, url FROM images WHERE name = %s AND phone = %s", (name, phone)).fetchone()
    if row is None or row["measurement"] is None:
        raise CaseError(f"No measurement {measurement_id}. Use a measurement_id from segment_image.")
    case["measurements"] = normalized(case)["measurements"]
    if any(m["id"] == measurement_id for m in case["measurements"]):
        return []
    step = None
    if step_id is not None and (step := next((s for s in case["steps"] if s["id"] == step_id), None)) is None:
        raise CaseError(f"No step {step_id} in this case.")

    record = row["measurement"]
    url = row["url"] or media_url(name)
    said: list[str] = []
    captions: list[str] = []
    rose = False
    for metric, value, label in (
        ("lesion", record.get("lesion_pct"), ""),
        ("pests", record.get("pest_count"), record.get("pest_label", "")),
    ):
        if value is None:
            continue
        previous = next((m for m in reversed(case["measurements"]) if m["metric"] == metric), None)
        if previous is None and not value:
            continue
        change = None if previous is None else measured_change(metric, previous["value"], value)
        case["measurements"] = [
            *case["measurements"],
            {"id": measurement_id, "url": url, "metric": metric, "value": value, "label": label, "at": _now(), "step_id": step_id, "change": change},
        ][-MAX_MEASUREMENTS:]
        now = _shown(metric, value, label)
        captions.append(f"পাতার {now} আক্রান্ত" if metric == "lesion" else now)
        if previous is None:
            said.append(f"প্রথম মাপ: {captions[-1]}")
            continue
        before = _shown(metric, previous["value"], previous["label"])
        said.append(f"ছবিতে মাপা: {before} থেকে {now}")
        if change == "worse":
            rose = True
            if step is not None:
                step["outcome"], step["status"] = "worse", "attention"
                step["note"] = f"ছবিতে মাপা {before} থেকে বেড়ে {now} হয়েছে"
    if not any(p["url"] == url for p in case["photos"]):
        case["photos"] = [*case["photos"], {"url": url, "caption": " · ".join(captions), "at": _now()}][-MAX_PHOTOS:]
    if rose and case["stage"] == "in_treatment":
        case["stage"] = "escalated"
        words = CULTIVATION_STAGE_WORDS if case["plan_type"] == "cultivation" else STAGE_WORDS
        said.append(f"অবস্থা: {words['escalated']}")
    return said


def _write(conn: Connection, phone: str, case: dict, *, insert: bool = False) -> None:
    case["updated_at"] = _now()
    if insert:
        conn.execute(
            "INSERT INTO crop_cases (id, phone, data, updated_at) VALUES (%s, %s, %s, %s)",
            (case["id"], phone, Jsonb(case), case["updated_at"]),
        )
    else:
        conn.execute(
            "UPDATE crop_cases SET data = %s, updated_at = %s WHERE id = %s AND phone = %s",
            (Jsonb(case), case["updated_at"], case["id"], phone),
        )


def create_case(
    phone: str,
    *,
    crop: str,
    problem: str,
    plot: str,
    diagnosis: str,
    confidence: Confidence | None,
    steps: list[PlanStepInput],
    warning_signs: list[str],
    next_step: str,
    end_date: str | None,
    thread_id: str | None,
    plan_type: PlanType = "treatment",
    start_date: str | None = None,
    anchor_label: str = "",
    baseline_measurement_id: str | None = None,
) -> dict:
    if not steps:
        raise CaseError("The plan is empty. List what the farmer should do and when to check in `steps`.")
    limit = MAX_STEPS_BY_TYPE[plan_type]
    if len(steps) > limit:
        raise CaseError(f"The plan has more than {limit} steps. Merge the small ones.")
    try:
        start = _iso_date(start_date)
    except ValueError as e:
        raise CaseError(f"start_date: {e}") from None
    if start is None and any(s.day is not None for s in steps):
        raise CaseError("Steps are given as `day`s, so start_date (the day they count from) is needed.")
    built = new_steps(steps, start_date=start)
    try:
        end = _iso_date(end_date) or max((s["due"] for s in built if s["due"]), default=None)
    except ValueError as e:
        raise CaseError(f"end_date: {e}") from None

    with farmer(phone) as conn:
        # Lock the farmer's row so two cases started at once cannot both pass the limit.
        conn.execute("SELECT 1 FROM farmers WHERE phone = %s FOR UPDATE", (phone,))
        if len(list_cases_in(conn, include_closed=False)) >= MAX_OPEN_CASES:
            raise CaseError(
                f"The farmer already has {MAX_OPEN_CASES} open cases. Ask which one is over "
                "(mark it resolved or abandoned) before starting another."
            )
        case = {
            "id": f"c{uuid.uuid4().hex[:10]}",
            "crop": _clip(crop, 40),
            "problem": _clip(problem, MAX_TITLE),
            "plot": _clip(plot, 60),
            "plan_type": plan_type,
            "diagnosis": _clip(diagnosis),
            "confidence": confidence or "high",
            "start_date": start,
            "anchor_label": _clip(anchor_label, 40),
            "stage": "in_treatment",
            "started_on": date.today().isoformat(),
            "end_date": end,
            "next_step": _clip(next_step),
            "warning_signs": [_clip(w, 160) for w in warning_signs[:6] if w.strip()],
            "steps": built,
            "photos": [],
            "measurements": [],
            "thread_id": thread_id,
            "created_at": _now(),
            "activity": [_event(AGENT, f"{len(steps)}টি ধাপের পরিকল্পনা শুরু হলো")],
        }
        if baseline_measurement_id:
            said = _attach_measurement(conn, phone, case, baseline_measurement_id, None)
            case["activity"] += [_event(AGENT, t) for t in said]
        _write(conn, phone, case, insert=True)
    return case


def change_case(
    phone: str,
    case_id: str,
    *,
    changes: list[StepChange] = (),
    add_steps: list[PlanStepInput] = (),
    remove_step_ids: list[str] = (),
    add_photo: PhotoInput | None = None,
    stage: Stage | None = None,
    next_step: str | None = None,
    end_date: str | None = None,
    start_date: str | None = None,
    warning_signs: list[str] | None = None,
    add_measurement_id: str | None = None,
    measurement_step_id: str | None = None,
    actor: Actor = AGENT,
) -> dict:
    """Apply a set of changes at once, and log them as `actor`'s; nothing is
    saved if any of them fails (the transaction rolls back)."""
    with farmer(phone) as conn:
        return apply_changes(
            conn, phone, case_id,
            changes=changes, add_steps=add_steps, remove_step_ids=remove_step_ids, add_photo=add_photo,
            stage=stage, next_step=next_step, end_date=end_date, start_date=start_date,
            warning_signs=warning_signs, add_measurement_id=add_measurement_id,
            measurement_step_id=measurement_step_id, actor=actor,
        )


def log_event(conn: Connection, phone: str, case_id: str, text: str, *, actor: Actor = AGENT, stage: Stage | None = None) -> dict:
    """Add one line to a case's activity (and optionally move its stage), in an open transaction."""
    return apply_changes(conn, phone, case_id, stage=stage, note_event=text, actor=actor)


def apply_changes(
    conn: Connection,
    phone: str,
    case_id: str,
    *,
    changes: list[StepChange] = (),
    add_steps: list[PlanStepInput] = (),
    remove_step_ids: list[str] = (),
    add_photo: PhotoInput | None = None,
    stage: Stage | None = None,
    next_step: str | None = None,
    end_date: str | None = None,
    start_date: str | None = None,
    warning_signs: list[str] | None = None,
    note_event: str | None = None,
    add_measurement_id: str | None = None,
    measurement_step_id: str | None = None,
    actor: Actor = AGENT,
) -> dict:
    """change_case's work, in an open db.farmer() transaction."""
    row = conn.execute(
        "SELECT data FROM crop_cases WHERE id = %s AND phone = %s FOR UPDATE", (case_id, phone)
    ).fetchone()
    if row is None:
        raise CaseError(f"No case {case_id} for this farmer.")
    case = normalized(row["data"])
    words = CULTIVATION_STAGE_WORDS if case["plan_type"] == "cultivation" else STAGE_WORDS

    steps = case["steps"]
    by_id = {s["id"]: s for s in steps}
    before = {s["id"]: dict(s) for s in steps}
    said: list[str] = []

    for change in changes:
        step = by_id.get(change.step_id)
        if step is None:
            raise CaseError(f"No step {change.step_id} in this case. Its steps are: {', '.join(by_id)}.")
        if change.outcome is not None:
            step["outcome"] = change.outcome
            if change.status is None and step["status"] == "todo":
                step["status"] = "done"
        if change.status is not None:
            step["status"] = change.status
        if change.note is not None:
            step["note"] = _clip(change.note)
        if change.due is not None:
            step["due"] = change.due or None
            # A step moved by hand keeps counting from the start date at its new place.
            if step["day"] is not None:
                step["day"] = (
                    (date.fromisoformat(step["due"]) - date.fromisoformat(case["start_date"])).days
                    if step["due"] and case["start_date"]
                    else None
                )
    for step_id in dict.fromkeys(c.step_id for c in changes):
        said += _describe(before[step_id], by_id[step_id])

    removed = set(remove_step_ids)
    if unknown := removed - by_id.keys():
        raise CaseError(f"No step {', '.join(sorted(unknown))} in this case.")
    steps = [s for s in steps if s["id"] not in removed]
    said += [f'"{before[i]["title"]}" বাদ দেওয়া হলো' for i in remove_step_ids]

    if start_date is not None:
        try:
            new_start = _iso_date(start_date)
        except ValueError as e:
            raise CaseError(f"start_date: {e}") from None
        if new_start and new_start != case["start_date"]:
            old = case["start_date"]
            case["start_date"] = new_start
            moved = 0
            for step in steps:
                if step["day"] is not None:
                    step["due"] = _due_from(new_start, step["day"])
                    moved += 1
            if old and case["end_date"]:
                shift = (date.fromisoformat(new_start) - date.fromisoformat(old)).days
                case["end_date"] = (date.fromisoformat(case["end_date"]) + timedelta(days=shift)).isoformat()
            label = case["anchor_label"] or "শুরুর তারিখ"
            said.append(f"{label} সরে {_bn_date(new_start)} হলো" + (f"; {moved}টি ধাপের তারিখ সেই হিসাবে সরানো হলো" if moved else ""))

    if any(s.day is not None for s in add_steps) and not case["start_date"]:
        raise CaseError("New steps are given as `day`s, but this plan has no start_date; give `due` dates instead.")
    added = new_steps(list(add_steps), start=_next_step_number(steps), start_date=case["start_date"])
    steps += added
    limit = MAX_STEPS_BY_TYPE[case["plan_type"]]
    if len(steps) > limit:
        raise CaseError(f"The plan would have more than {limit} steps. Merge the small ones.")
    said += [f'নতুন ধাপ: "{s["title"]}"' for s in added]
    case["steps"] = steps

    if add_photo is not None:
        if not add_photo.url.startswith(("http://", "https://")):
            raise CaseError("add_photo.url must be an annotated_image_url from segment_image.")
        case["photos"] = [*case["photos"], {"url": add_photo.url, "caption": _clip(add_photo.caption, 120), "at": _now()}][-MAX_PHOTOS:]
        said.append("ছবি যোগ হলো" + (f": {add_photo.caption}" if add_photo.caption else ""))
    if stage is not None and stage != case["stage"]:
        case["stage"] = stage
        said.append(f"অবস্থা: {words[stage]}")
    if next_step is not None:
        case["next_step"] = _clip(next_step)
    if warning_signs is not None:
        case["warning_signs"] = [_clip(w, 160) for w in warning_signs[:6] if w.strip()]
    if end_date is not None:
        try:
            end = _iso_date(end_date)
        except ValueError as e:
            raise CaseError(f"end_date: {e}") from None
        if end != case["end_date"]:
            case["end_date"] = end
            said.append(f"শেষ চেকআপ {end}" if end else "শেষ চেকআপের তারিখ সরানো হলো")
    # Last: evidence of a rise stands over any outcome or stage set in this same call.
    if add_measurement_id:
        said += _attach_measurement(conn, phone, case, add_measurement_id, measurement_step_id)
    if note_event:
        said.append(_clip(note_event))
    if said:
        case["activity"] = [*case["activity"], *(_event(actor, t) for t in said)][-MAX_ACTIVITY:]

    _write(conn, phone, case)
    return case


def delete_case(phone: str, case_id: str) -> bool:
    with farmer(phone) as conn:
        cur = conn.execute("DELETE FROM crop_cases WHERE id = %s AND phone = %s", (case_id, phone))
        return cur.rowcount > 0

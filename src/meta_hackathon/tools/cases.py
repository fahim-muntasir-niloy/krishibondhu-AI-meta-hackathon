"""Tracking a crop problem's treatment plan with the farmer, in a pane beside
the web chat (cases.py has the data and the rules).

Once a diagnosis is made and the farmer is going to treat it, the agent starts
a case: the plan as dated steps, from today to the last check. As the farmer
does steps and reports how the plants look, the agent records it, adjusts the
plan, and escalates to an officer when it is getting worse.

Each tool returns the case, as the web UI shows it, as the ToolMessage's
`artifact`, which the model never sees; the UI opens or refreshes the pane
from it. The model gets the plan in a compact form, with the ids it needs for
the next change.

A case belongs to the farmer (their phone), not to the thread: the system
prompt lists the open ones every turn, so the agent picks up where the farmer
left off in any conversation.

The store blocks, so these are sync tools: LangChain runs them in a thread.
"""

from langchain.tools import ToolException, ToolRuntime, tool

from meta_hackathon.agent.context import UserContext, phone_number
from meta_hackathon.cases import (
    CaseError,
    Confidence,
    PhotoInput,
    PlanStepInput,
    Stage,
    StepChange,
    case_for_model,
    case_view,
    change_case,
    create_case,
    get_case,
    list_cases,
)

_SHOWN = "The plan is shown in the tracker pane beside the chat; do not repeat the steps in your reply."


def _thread(runtime: ToolRuntime) -> str | None:
    return (runtime.config or {}).get("configurable", {}).get("thread_id")


def _phone(runtime: ToolRuntime) -> str:
    phone = phone_number(runtime)
    if not phone:
        raise ToolException("No farmer identity on this request, so there is nowhere to save a case.")
    return phone


@tool(response_format="content_and_artifact")
def start_crop_case(
    crop: str,
    problem: str,
    steps: list[PlanStepInput],
    confidence: Confidence,
    *,
    runtime: ToolRuntime[UserContext],
    diagnosis: str = "",
    plot: str = "",
    warning_signs: list[str] | None = None,
    next_step: str = "",
    end_date: str | None = None,
    baseline_measurement_id: str | None = None,
) -> tuple[str, dict]:
    """Start tracking a crop problem's treatment plan, in a pane beside the chat.

    Use it once you have diagnosed a problem (from a photo or a clear description)
    and given the treatment, so the farmer can follow the plan day by day. Not for
    general questions, and not when you are unsure what the problem is.

    - crop, problem: Bangla, e.g. "ধান", "ধানের ব্লাস্ট রোগ". plot: which field, if the farmer said.
    - diagnosis: one Bangla sentence on what you saw and why you think so.
    - confidence: high, medium or low.
    - steps: the plan in order. "action" steps are what the farmer does (spray, drain water,
      remove leaves), with the dose and time in `details` and PPE / waiting period in
      `safety_note`. Add "check" steps for follow-ups: a midpoint check and a final check
      for plans of 4-7 days, every 3-4 days for longer ones. Give every step a `due` date.
    - warning_signs: up to 4 short Bangla signs that mean "tell us at once".
    - next_step: the first thing to do, in one Bangla sentence.
    - end_date: YYYY-MM-DD of the last check; defaults to the last step's date.
    - baseline_measurement_id: measurement_id from segment_image on the farmer's photo, the
      day-0 figure that later photos are compared with.
    """
    try:
        case = create_case(
            _phone(runtime),
            crop=crop,
            problem=problem,
            plot=plot,
            diagnosis=diagnosis,
            confidence=confidence,
            steps=steps,
            warning_signs=warning_signs or [],
            next_step=next_step,
            end_date=end_date,
            thread_id=_thread(runtime),
            baseline_measurement_id=baseline_measurement_id,
        )
    except CaseError as e:
        raise ToolException(f"The case was not started: {e}") from e
    view = case_view(case)
    return f"Started the case. {_SHOWN}\n{case_for_model(view)}", view


@tool(response_format="content_and_artifact")
def start_cultivation_plan(
    crop: str,
    title: str,
    start_date: str,
    anchor_label: str,
    steps: list[PlanStepInput],
    *,
    runtime: ToolRuntime[UserContext],
    goal: str = "",
    plot: str = "",
    warning_signs: list[str] | None = None,
    next_step: str = "",
) -> tuple[str, dict]:
    """Start a plan for growing something, start to finish, in the pane beside the chat:
    a crop season (Boro rice, potato, mustard), mushrooms, a seedbed, or a fertiliser or
    irrigation schedule. For a crop problem use start_crop_case instead.

    Ask first for what you need: the crop and variety, how much land, and the start date
    (when they sowed, transplanted or will; for mushrooms, the spawning day).

    - title: Bangla, e.g. "বোরো ধান চাষ (ব্রি ধান৮৯)", "ঝিনুক মাশরুম চাষ".
    - start_date: YYYY-MM-DD of day 0; anchor_label says what day 0 is, e.g. "চারা রোপণ",
      "বীজ বপন", "স্পন রাখা".
    - goal: one Bangla sentence, e.g. "৩ বিঘায় বোরো ধান, হেক্টরে ৭ টনের লক্ষ্য".
    - steps: every step with `day` (days from start_date; negative before it, e.g. seedbed
      at -35) and `phase` (জমি তৈরি, বীজতলা, রোপণ, সার প্রয়োগ, সেচ, আগাছা দমন, রোগ-পোকা নজর,
      ফসল কাটা ...), in order. Doses and amounts per bigha in `details`, with `source` for
      every dose. Add "check" steps at key stages (e.g. tillering, flowering) to look at the
      crop and send a photo. Up to 40 steps; keep each one a real task.
    - warning_signs: up to 4 short Bangla signs to report at once.
    - next_step: the first thing to do, one Bangla sentence.
    """
    try:
        case = create_case(
            _phone(runtime),
            crop=crop,
            problem=title,
            plot=plot,
            diagnosis=goal,
            confidence=None,
            steps=steps,
            warning_signs=warning_signs or [],
            next_step=next_step,
            end_date=None,
            thread_id=_thread(runtime),
            plan_type="cultivation",
            start_date=start_date,
            anchor_label=anchor_label,
        )
    except CaseError as e:
        raise ToolException(f"The plan was not started: {e}") from e
    view = case_view(case)
    return f"Started the plan. {_SHOWN}\n{case_for_model(view)}", view


@tool(response_format="content_and_artifact")
def update_crop_case(
    case_id: str,
    *,
    runtime: ToolRuntime[UserContext],
    steps: list[StepChange] | None = None,
    add_steps: list[PlanStepInput] | None = None,
    remove_step_ids: list[str] | None = None,
    add_photo: PhotoInput | None = None,
    stage: Stage | None = None,
    next_step: str | None = None,
    end_date: str | None = None,
    start_date: str | None = None,
    warning_signs: list[str] | None = None,
    add_measurement_id: str | None = None,
    measurement_step_id: str | None = None,
) -> tuple[str, dict]:
    """Record progress on one of the farmer's plans (treatment or cultivation).

    - steps: changes to existing steps by step_id. Mark an action "done" when the farmer
      says they did it. For a check, set `outcome` (better, same, worse) from what the
      farmer reports or what a new photo shows, with a `note` on what you see; use status
      "attention" when it is worse or something went wrong. `due` moves a step.
    - add_steps / remove_step_ids: when the plan changes (e.g. a second spray, another check).
    - add_measurement_id: after segment_image on a follow-up photo, its measurement_id (this
      also files the photo; no add_photo needed). It is compared with the last measurement.
      A clear rise (leaf damage or insect count) marks measurement_step_id (the check step) worse
      and escalates the case by itself, whatever the farmer reported. A fall changes nothing by
      itself: look at the photo, and only then set the outcome. The result says what happened.
    - add_photo: a follow-up photo with no measurement: file its annotated_image_url
      with a caption, so before and after can be compared.
    - stage: in_treatment, escalated (worse, or an officer is needed), resolved (recovered),
      abandoned (the farmer stopped).
    - next_step: the one thing to do next, in one Bangla sentence. Update it with every change.
    - end_date: YYYY-MM-DD. When it moves, move the steps' dates too.
    - start_date: cultivation plans, YYYY-MM-DD: when day 0 turns out to be another day (the
      farmer transplanted later); every step counted from it moves with it.
    - stage for a cultivation plan: escalated when a problem came up (then start a crop case
      for it), resolved when harvested / finished.

    All the changes are made together, or none are.
    """
    try:
        case = change_case(
            _phone(runtime),
            case_id,
            changes=steps or [],
            add_steps=add_steps or [],
            remove_step_ids=remove_step_ids or [],
            add_photo=add_photo,
            stage=stage,
            next_step=next_step,
            end_date=end_date,
            start_date=start_date,
            warning_signs=warning_signs,
            add_measurement_id=add_measurement_id,
            measurement_step_id=measurement_step_id,
        )
    except CaseError as e:
        raise ToolException(f"Nothing was changed: {e}") from e
    view = case_view(case)
    return f"Updated the case. {_SHOWN}\n{case_for_model(view)}", view


@tool(response_format="content_and_artifact")
def get_crop_case(*, runtime: ToolRuntime[UserContext], case_id: str | None = None) -> tuple[str, dict | None]:
    """Read one of the farmer's crop cases in full and show it in the tracker pane,
    or, without case_id, list all of them.

    Read a case before changing it if you have not seen its steps in this
    conversation, and when the farmer asks how their treatment is going.
    """
    phone = _phone(runtime)
    if case_id is None:
        cases = list_cases(phone)
        if not cases:
            return "The farmer has no crop cases.", None
        lines = [f"- {c['problem']} on {c['crop']} (case_id: {c['id']}) -- {c['stage']}" for c in cases]
        return "The farmer's crop cases:\n" + "\n".join(lines), None
    case = get_case(phone, case_id)
    if case is None:
        raise ToolException(f"The farmer has no case {case_id}.")
    view = case_view(case)
    return f"{_SHOWN}\n{case_for_model(view)}", view


for _t in (start_crop_case, start_cultivation_plan, update_crop_case, get_crop_case):
    # A ToolException becomes an error ToolMessage the model can read and fix.
    _t.handle_tool_error = True

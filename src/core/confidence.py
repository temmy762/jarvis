from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_TRELLO_ID_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)


@dataclass
class ConfidenceAssessment:
    score: int
    awaiting: Optional[str] = None
    question: Optional[str] = None
    missing: Optional[List[str]] = None


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _is_email(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def _looks_like_trello_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_TRELLO_ID_RE.match(value.strip()))


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_any(args: Dict[str, Any], keys: List[str]) -> bool:
    for k in keys:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return True
    return False


def _parse_iso_dt(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _schema_required_fields(tool_schema: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(tool_schema, dict):
        return []
    fn = tool_schema.get("function")
    if not isinstance(fn, dict):
        return []
    params = fn.get("parameters")
    if not isinstance(params, dict):
        return []
    req = params.get("required")
    if isinstance(req, list):
        return [str(x) for x in req if isinstance(x, str)]
    return []


def _default_question(field: str) -> str:
    questions = {
        "card_name": "Which Trello task/card should I use?",
        "board_name": "Which Trello board is this on?",
        "list_name": "Which Trello list should I use?",
        "list_id": "Which Trello list should I use?",
        "to_list_name": "Which Trello list should I move it to?",
        "title": "What is the title?",
        "event_title": "Which calendar event is this?",
        "event_id": "Which calendar event should I target?",
        "to": "Who should I email?",
        "subject": "What should the email subject be?",
        "body": "What should the email say?",
        "query": "What should I search for?",
    }
    return questions.get(field, f"Please provide {field}.")


def compute_tool_confidence(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_schema: Optional[Dict[str, Any]] = None,
) -> ConfidenceAssessment:
    name = str(tool_name or "").strip()
    args = tool_args if isinstance(tool_args, dict) else {}

    missing: List[str] = []
    awaiting: Optional[str] = None
    question: Optional[str] = None

    intent = 0.85
    completeness = 0.85
    uniqueness = 0.85
    feasibility = 0.90

    required = _schema_required_fields(tool_schema)
    for f in required:
        v = args.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)

    if name == "trello_dispatch":
        action = (args.get("action") or "").strip().lower() if isinstance(args.get("action"), str) else ""
        fields = args.get("fields") if isinstance(args.get("fields"), dict) else None

        if not action:
            intent = 0.60
        else:
            intent = 0.92

        if action in {"update", "move", "comment", "delete", "archive"}:
            if not (_has_any(args, ["card_id"]) or _has_any(args, ["card_name"])):
                missing.append("card_name")
            if not (_has_any(args, ["board_id"]) or _has_any(args, ["board_name"])) and not _has_any(args, ["card_id"]):
                missing.append("board_name")

        if action == "move":
            if not (_has_any(args, ["to_list_id"]) or _has_any(args, ["to_list_name"])):
                missing.append("to_list_name")

        if action == "update":
            if not isinstance(fields, dict) or not fields:
                intent = min(intent, 0.70)
                completeness = min(completeness, 0.60)

        if _has_any(args, ["card_id"]) and _looks_like_trello_id(str(args.get("card_id"))):
            uniqueness = 0.98
        elif _has_any(args, ["card_name"]) and (_has_any(args, ["board_id"]) or _has_any(args, ["board_name"])):
            uniqueness = 0.88
        elif _has_any(args, ["card_name"]):
            uniqueness = 0.70
        else:
            uniqueness = 0.55

        if _has_any(args, ["card_id"]) and not _looks_like_trello_id(str(args.get("card_id"))):
            feasibility = 0.55

    elif name == "trello_get_card_status":
        intent = 0.95
        has_card_id = _has_any(args, ["card_id"]) and _looks_like_trello_id(str(args.get("card_id")))
        has_card_name = _has_any(args, ["card_name"]) or (
            _has_any(args, ["card_id"]) and isinstance(args.get("card_id"), str) and not _looks_like_trello_id(str(args.get("card_id")))
        )
        has_board = _has_any(args, ["board_id", "board_name"])

        if not has_card_id and not has_card_name:
            missing.append("card_name")
        if has_card_name and not has_card_id and not has_board:
            uniqueness = 0.72
            missing.append("board_name")
        if has_card_id:
            uniqueness = 0.98
        elif has_card_name and has_board:
            uniqueness = 0.88

    elif name == "trello_list_cards":
        intent = 0.92
        has_list_id = _has_any(args, ["list_id"]) and _looks_like_trello_id(str(args.get("list_id")))
        has_list_name = _has_any(args, ["list_name"]) or (
            _has_any(args, ["list_id"]) and isinstance(args.get("list_id"), str) and not _looks_like_trello_id(str(args.get("list_id")))
        )
        has_board = _has_any(args, ["board_id", "board_name"])

        if not has_list_id and not has_list_name:
            missing.append("list_name")
        if has_list_name and not has_list_id and not has_board:
            uniqueness = 0.70
            missing.append("board_name")
        if has_list_id:
            uniqueness = 0.98
        elif has_list_name and has_board:
            uniqueness = 0.88

        if _has_any(args, ["list_id"]) and isinstance(args.get("list_id"), str) and args.get("list_id").strip() and not (
            _looks_like_trello_id(str(args.get("list_id")))
        ) and not _has_any(args, ["list_name"]):
            # Model sometimes puts a list name into list_id; treat as list_name.
            pass

    elif name in {"gmail_send_email", "gmail_send_draft"}:
        intent = 0.95
        if name == "gmail_send_email":
            if not _is_email(args.get("to")):
                missing.append("to")
                feasibility = 0.60
            if not _is_nonempty(args.get("subject")):
                missing.append("subject")
            if not _is_nonempty(args.get("body")):
                missing.append("body")

    elif name in {"calendar_create_meet_event", "calendar_create_event", "calendar_create_event_safe"}:
        intent = 0.92
        if not _is_nonempty(args.get("title")) and not _is_nonempty(args.get("summary")):
            missing.append("title")
        start_ok = _parse_iso_dt(args.get("start_time")) or _parse_iso_dt(args.get("start")) or _parse_iso_dt(args.get("start_iso"))
        if not start_ok:
            missing.append("start_time")
        end_ok = _parse_iso_dt(args.get("end_time")) or _parse_iso_dt(args.get("end")) or _parse_iso_dt(args.get("end_iso"))
        if not end_ok:
            missing.append("end_time")
        uniqueness = 0.85

    elif name in {"calendar_cancel_meeting", "calendar_add_note_to_meeting", "calendar_update_attendees", "calendar_reschedule_meeting"}:
        intent = 0.92
        if not _has_any(args, ["event_id"]) and not _has_any(args, ["title", "event_title"]):
            missing.append("event_title")
        if _has_any(args, ["event_id"]):
            uniqueness = 0.98
        else:
            uniqueness = 0.72

    else:
        if missing:
            completeness = 0.70

    if missing:
        completeness = min(completeness, max(0.40, 1.0 - 0.20 * min(len(missing), 4)))

    if missing:
        awaiting = missing[0]
        question = _default_question(awaiting)

    score_f = (
        0.25 * _clamp01(intent)
        + 0.30 * _clamp01(completeness)
        + 0.25 * _clamp01(uniqueness)
        + 0.20 * _clamp01(feasibility)
    )

    score = int(round(100.0 * _clamp01(score_f)))

    if missing and score >= 90:
        score = 89

    return ConfidenceAssessment(score=score, awaiting=awaiting, question=question, missing=missing or None)


def format_confidence_prefix(score: int) -> str:
    try:
        s = int(score)
    except Exception:
        s = 0
    if s < 0:
        s = 0
    if s > 100:
        s = 100
    return f"I'm {s}% sure — proceeding."

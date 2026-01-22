from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class OwnerPreferences:
    decisive_action: bool = True
    minimize_confirmations: bool = True
    trust_calendar: bool = True
    trust_email: bool = True


DEFAULT_OWNER_PREFERENCES = OwnerPreferences()


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _title_score(query_title: str, event_title: str) -> float:
    q = _norm_text(query_title)
    e = _norm_text(event_title)
    if not q or not e:
        return 0.0
    if q == e:
        return 1.0
    if q in e or e in q:
        return 0.92
    return float(SequenceMatcher(a=q, b=e).ratio())


def _safe_parse_dt(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _date_score(date_str: Optional[str], event_start_iso: Optional[str]) -> Optional[float]:
    if not date_str:
        return None
    dt = _safe_parse_dt(event_start_iso)
    if not dt:
        return 0.0
    try:
        return 1.0 if dt.date().isoformat() == str(date_str) else 0.0
    except Exception:
        return 0.0


def _time_window_score(time_min: Optional[str], time_max: Optional[str], event_start_iso: Optional[str]) -> Optional[float]:
    if not (time_min and time_max):
        return None
    start = _safe_parse_dt(event_start_iso)
    tmin = _safe_parse_dt(time_min)
    tmax = _safe_parse_dt(time_max)
    if not (start and tmin and tmax):
        return 0.0
    if tmin <= start <= tmax:
        return 1.0
    return 0.0


def compute_intent_confidence(
    *,
    query_title: str,
    date_str: Optional[str],
    time_min: Optional[str],
    time_max: Optional[str],
    candidate: Dict[str, Any],
) -> float:
    t_score = _title_score(query_title, str(candidate.get("title") or ""))
    d_score = _date_score(date_str, candidate.get("start"))
    w_score = _time_window_score(time_min, time_max, candidate.get("start"))

    weights: List[Tuple[Optional[float], float]] = [
        (t_score, 0.45),
        (d_score, 0.35),
        (w_score, 0.20),
    ]

    total_w = 0.0
    total = 0.0
    for val, w in weights:
        if val is None:
            continue
        total += float(val) * w
        total_w += w

    if total_w <= 0:
        return 0.0

    conf = total / total_w
    if conf < 0.0:
        return 0.0
    if conf > 1.0:
        return 1.0
    return conf


def choose_best_match(
    *,
    query_title: str,
    date_str: Optional[str],
    time_min: Optional[str],
    time_max: Optional[str],
    matches: List[Dict[str, Any]],
    confidence_threshold: float = 0.85,
    separation_threshold: float = 0.12,
) -> Dict[str, Any]:
    scored: List[Tuple[float, int]] = []
    for idx, m in enumerate(matches):
        conf = compute_intent_confidence(
            query_title=query_title,
            date_str=date_str,
            time_min=time_min,
            time_max=time_max,
            candidate=m,
        )
        scored.append((conf, idx))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return {"chosen": None, "confidence": 0.0, "index": None}

    best_conf, best_idx = scored[0]
    second_conf = scored[1][0] if len(scored) > 1 else 0.0

    if best_conf >= confidence_threshold and (best_conf - second_conf) >= separation_threshold:
        return {"chosen": matches[best_idx], "confidence": float(best_conf), "index": int(best_idx)}

    return {"chosen": None, "confidence": float(best_conf), "index": None}


def decide_requires_confirmation(
    *,
    domain: str,
    action: str,
    risk: RiskLevel,
    confidence: float,
    prefs: OwnerPreferences = DEFAULT_OWNER_PREFERENCES,
    confidence_threshold: float = 0.85,
) -> bool:
    trusted = (
        (domain == "calendar" and prefs.trust_calendar)
        or (domain == "email" and prefs.trust_email)
    )

    # If the owner hasn't granted trust for this domain, be conservative.
    if not trusted:
        return True

    # High risk is always confirmation-required.
    if risk == RiskLevel.LOW:
        return False
    if risk == RiskLevel.MEDIUM:
        return not (confidence >= confidence_threshold)
    return True

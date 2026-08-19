"""후보(candidate dict) → 맥 캘린더 이벤트 변환/추가 공용 헬퍼."""
from __future__ import annotations

from datetime import datetime, timedelta

from .calendar_mac import add_event

NO_COURSE = "(분류 없음)"


def course_key(c: dict) -> str:
    """그룹(구독) 키. 강좌명 기준. 비어있으면 기본값."""
    return (c.get("course") or "").strip() or NO_COURSE


def build_event_fields(c: dict):
    """catalog/pending 의 직렬화된 후보(due_iso 보유)에서 이벤트 필드 생성."""
    if not c.get("due_iso"):
        return None
    due = datetime.fromisoformat(c["due_iso"])
    all_day = bool(c.get("allday"))
    start = due
    end = due if all_day else due + timedelta(minutes=30)
    summary = f"[{c['type_label']}] {c['title']}"
    desc_lines = [f"강좌: {c.get('course', '')}", f"유형: {c['type_label']}", "출처: eCampus 동기화"]
    if c.get("url"):
        desc_lines.append(c["url"])
    return summary, start, end, "\n".join(desc_lines), all_day


def add_candidate(cfg: dict, c: dict) -> bool:
    """후보를 캘린더에 추가. 성공 시 True. 마감 없으면 False."""
    fields = build_event_fields(c)
    if not fields:
        return False
    summary, start, end, desc, all_day = fields
    add_event(cfg["calendar_name"], summary, start, end, desc,
              reminder_minutes=cfg.get("reminder_minutes"), all_day=all_day)
    return True

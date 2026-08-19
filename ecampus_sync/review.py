"""검토 대기 목록을 보고 원하는 항목만 골라 맥 캘린더에 추가.

실행:  python3 -m ecampus_sync.review
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from .calendar_mac import add_event
from .config import load_config
from .ecampus import KST
from .store import load_pending, save_pending, load_state, save_state


def parse_selection(text: str, n: int) -> list[int]:
    """'1,3,5-7' → [0,2,4,5,6] (0-based, 범위 내만)."""
    idxs: set[int] = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                for i in range(int(a), int(b) + 1):
                    idxs.add(i - 1)
        elif part.isdigit():
            idxs.add(int(part) - 1)
    return sorted(i for i in idxs if 0 <= i < n)


def show(pending: list[dict]) -> None:
    print("\n=== eCampus 검토 대기 목록 ===")
    if not pending:
        print("  (없음)")
        return
    now = datetime.now(KST)
    for i, c in enumerate(pending, 1):
        due_iso = c.get("due_iso")
        dleft = ""
        if due_iso:
            try:
                d = datetime.fromisoformat(due_iso)
                days = (d - now).days
                dleft = f"  (D-{days})" if days >= 0 else f"  (지남 {-days}일)"
            except ValueError:
                pass
        print(f"  {i:2d}. [{c['type_label']}] {c['title']}")
        print(f"      마감 {c.get('due','?')}{dleft}   ·   {c.get('course','')}")


def build_event_fields(c: dict):
    summary = f"[{c['type_label']}] {c['title']}"
    due = datetime.fromisoformat(c["due_iso"]) if c.get("due_iso") else None
    all_day = bool(c.get("allday"))
    if due is None:
        return None
    start = due
    end = due if all_day else due + timedelta(minutes=30)
    desc_lines = [f"강좌: {c.get('course','')}", f"유형: {c['type_label']}", "출처: eCampus 동기화"]
    if c.get("url"):
        desc_lines.append(c["url"])
    return summary, start, end, "\n".join(desc_lines), all_day


def main() -> int:
    cfg = load_config()
    state = load_state()
    _added = set(state["added"])
    # 카탈로그에서 아직 캘린더에 없는 것만
    pending = [c for c in load_pending() if c["uid"] not in _added]

    if not pending:
        print("검토할 항목이 없습니다. 먼저 수집을 실행하세요:  python3 -m ecampus_sync.fetch")
        return 0

    show(pending)
    print("\n명령:")
    print("  숫자          예) 1,3,5-7   → 캘린더에 추가")
    print("  a             전체 추가")
    print("  d 숫자        예) d 2,4     → 무시(다시 안 보이게)")
    print("  q 또는 엔터   그만두기")

    try:
        raw = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0

    if not raw or raw.lower() == "q":
        print("변경 없음.")
        return 0

    dismiss = raw.lower().startswith("d ") or raw.lower().startswith("d,")
    if dismiss:
        sel = parse_selection(raw[1:], len(pending))
        for i in sel:
            state["dismissed"].append(pending[i]["uid"])
        chosen_uids = {pending[i]["uid"] for i in sel}
        state["dismissed"] = sorted(set(state["dismissed"]))
        save_state(state)
        save_pending([c for c in pending if c["uid"] not in chosen_uids])
        print(f"{len(sel)}건 무시 처리했습니다.")
        return 0

    sel = list(range(len(pending))) if raw.lower() in ("a", "all") else parse_selection(raw, len(pending))
    if not sel:
        print("선택된 항목이 없습니다.")
        return 0

    added_ok, failed = [], []
    for i in sel:
        c = pending[i]
        fields = build_event_fields(c)
        if fields is None:
            failed.append((c, "마감 시각 없음"))
            continue
        summary, start, end, desc, all_day = fields
        try:
            add_event(cfg["calendar_name"], summary, start, end, desc,
                      reminder_minutes=cfg.get("reminder_minutes"), all_day=all_day)
            added_ok.append(c)
            print(f"  ✅ 추가: {summary}  ({c.get('due','')})")
        except Exception as e:  # noqa: BLE001
            failed.append((c, str(e)))
            print(f"  ❌ 실패: {summary} — {e}")

    if added_ok:
        state["added"].extend(c["uid"] for c in added_ok)
        state["added"] = sorted(set(state["added"]))
        save_state(state)
        added_uids = {c["uid"] for c in added_ok}
        save_pending([c for c in pending if c["uid"] not in added_uids])

    print(f"\n완료: {len(added_ok)}건 추가"
          + (f", {len(failed)}건 실패" if failed else "")
          + f'.  캘린더 "{cfg["calendar_name"]}" 확인하세요.')
    return 0


if __name__ == "__main__":
    sys.exit(main())

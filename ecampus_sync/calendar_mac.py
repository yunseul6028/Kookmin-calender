"""macOS 기본 캘린더에 이벤트 추가 (AppleScript).

날짜는 문자열 파싱 대신 구성요소(year/month/day...)로 지정해 로케일 문제를 피한다.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta


def _as_str(s: str) -> str:
    """AppleScript 문자열 리터럴용 이스케이프."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _set_date_var(varname: str, dt: datetime) -> str:
    """dt 를 AppleScript date 변수로 만드는 스니펫."""
    return (
        f"set {varname} to (current date)\n"
        f"set day of {varname} to 1\n"          # 월말 오버플로 방지
        f"set year of {varname} to {dt.year}\n"
        f"set month of {varname} to {dt.month}\n"
        f"set day of {varname} to {dt.day}\n"
        f"set hours of {varname} to {dt.hour}\n"
        f"set minutes of {varname} to {dt.minute}\n"
        f"set seconds of {varname} to 0\n"
    )


def add_event(calendar_name: str, summary: str, start: datetime,
              end: datetime | None = None, description: str = "",
              reminder_minutes: int | None = None, all_day: bool = False) -> None:
    """지정 캘린더에 이벤트 추가. 캘린더가 없으면 생성."""
    if end is None:
        end = start + timedelta(hours=1)

    cal = _as_str(calendar_name)
    props = [f'summary:"{_as_str(summary)}"', "start date:startDate", "end date:endDate"]
    if description:
        props.append(f'description:"{_as_str(description)}"')
    if all_day:
        props.append("allday event:true")
    props_str = "{" + ", ".join(props) + "}"

    alarm = ""
    if reminder_minutes is not None:
        alarm = (
            "tell newEvent\n"
            f"  make new display alarm at end with properties {{trigger interval:-{int(reminder_minutes)}}}\n"
            "end tell\n"
        )

    # 캘린더가 없으면 자동 생성하지 않는다(자동 생성은 항상 로컬 계정에 생겨 iCloud로 안 감).
    # 없으면 명확히 에러 → 사용자가 iCloud에 해당 이름의 캘린더를 먼저 만들도록 안내.
    script = f"""
{_set_date_var("startDate", start)}
{_set_date_var("endDate", end)}
tell application "Calendar"
  if not (exists calendar "{cal}") then
    error "NO_CALENDAR"
  end if
  tell calendar "{cal}"
    set newEvent to make new event with properties {props_str}
    {alarm}
  end tell
end tell
"""
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr.strip()
        if "NO_CALENDAR" in err:
            raise RuntimeError(
                f'"{calendar_name}" 캘린더가 없습니다. Calendar 앱에서 '
                f'iCloud 아래에 "{calendar_name}" 캘린더를 먼저 만들어 주세요.'
            )
        raise RuntimeError(f"캘린더 추가 실패: {err}")

"""macOS 미리 알림(Reminders) 앱에 알림 추가 (AppleScript).

캘린더와 달리 목록(list) 자동 생성이 가능하다. 날짜는 구성요소로 지정(로케일 안전).
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timedelta


def _as_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _launch_reminders() -> None:
    subprocess.run(["open", "-gj", "-a", "Reminders"], capture_output=True)


def ensure_running() -> None:
    """배치 추가 전에 미리 알림 앱을 미리 띄워 -609/크래시를 줄인다."""
    _launch_reminders()
    time.sleep(2.5)


def _set_date_var(varname: str, dt: datetime) -> str:
    return (
        f"set {varname} to (current date)\n"
        f"set day of {varname} to 1\n"
        f"set year of {varname} to {dt.year}\n"
        f"set month of {varname} to {dt.month}\n"
        f"set day of {varname} to {dt.day}\n"
        f"set hours of {varname} to {dt.hour}\n"
        f"set minutes of {varname} to {dt.minute}\n"
        f"set seconds of {varname} to 0\n"
    )


def add_reminder(list_name: str, title: str, due: datetime,
                 body: str = "", remind_minutes_before: int | None = None) -> None:
    """지정 목록에 미리 알림 추가(목록 없으면 생성).

    주의: 미리 알림은 '마감(due date)'과 '알림(remind me date)'이 연동돼,
    알림을 앞당기면 마감일도 같이 당겨진다. 따라서 마감 시각에 알림이 울리도록
    둘 다 실제 마감으로 설정한다(마감일 정확성 우선). remind_minutes_before 는 무시.
    """
    remind = due
    lst = _as_str(list_name)

    props = [f'name:"{_as_str(title)}"', "due date:dueDate", "remind me date:remindDate"]
    if body:
        props.append(f'body:"{_as_str(body)}"')
    props_str = "{" + ", ".join(props) + "}"

    script = f"""
{_set_date_var("dueDate", due)}
{_set_date_var("remindDate", remind)}
tell application "Reminders"
  if not (exists list "{lst}") then make new list with properties {{name:"{lst}"}}
  tell list "{lst}"
    make new reminder with properties {props_str}
  end tell
end tell
"""
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    # -609(연결 무효)/-600(앱 미실행): 앱 띄우고 한 번 재시도
    if res.returncode != 0 and ("-609" in res.stderr or "-600" in res.stderr):
        _launch_reminders()
        time.sleep(3.0)
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"미리 알림 추가 실패: {res.stderr.strip()}")

"""state.json (중복 방지) / pending.json (검토 대기 목록) 입출력."""
from __future__ import annotations

import fcntl
import json
from pathlib import Path

from .config import STATE_PATH, PENDING_PATH

LOCK_PATH = STATE_PATH.with_suffix(".lock")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_state() -> dict:
    """
    state = {
      "seen":  ["uid", ...],   # 한 번이라도 후보로 보여준 항목
      "added": ["uid", ...],   # 실제로 캘린더에 추가한 항목
    }
    """
    st = _load(STATE_PATH, {})
    st.setdefault("seen", [])           # 후보로 한 번이라도 알림/표시한 uid
    st.setdefault("added", [])          # 캘린더에 추가한 uid
    st.setdefault("dismissed", [])      # (구버전) 무시 uid
    st.setdefault("subscriptions", [])  # 자동 등록 구독한 강좌(course) 목록
    st.setdefault("login_disabled", False)  # 로그인 실패로 자동 실행 중단 여부
    st.setdefault("login_error", "")        # 마지막 로그인 실패 메시지
    return st


def save_state(state: dict) -> None:
    _save(STATE_PATH, state)


def mutate_state(mutator):
    """여러 프로세스(수집기/웹서버/수동)가 동시에 state 를 고칠 때
    덮어쓰기(lost update)를 막기 위해 파일 잠금 아래에서 read-modify-write.
    mutator(state) 는 state dict 를 제자리에서 수정한다."""
    with open(LOCK_PATH, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            st = load_state()
            mutator(st)
            save_state(st)
            return st
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def load_pending() -> list:
    return _load(PENDING_PATH, [])


def save_pending(items: list) -> None:
    _save(PENDING_PATH, items)

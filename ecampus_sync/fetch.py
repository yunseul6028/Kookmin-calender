"""백그라운드 수집기 (launchd 로 매일 실행).

eCampus 에서 영상 수강기한 + 과제/일정을 모아 후보를 만들고,
아직 추가/무시하지 않은 것을 pending.json 에 기록한 뒤,
새로 등장한 항목이 있으면 macOS 알림을 띄운다.

실행:  python3 -m ecampus_sync.fetch
"""
from __future__ import annotations

import subprocess
import sys
import traceback
from datetime import datetime

from . import ecampus
from .config import LOG_PATH, load_config, get_password
from .ecampus import KST
from .events import add_candidate, course_key
from .store import load_state, save_state, save_pending, mutate_state


def log(msg: str) -> None:
    line = f"[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def notify(title: str, message: str) -> None:
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def gather_candidates(cfg: dict, manual: bool = False) -> list[dict]:
    capture = cfg.get("capture", {})
    candidates: list[dict] = []

    # 1) 영상 수강기한 — 로그인 필요 (실패 시 자동 실행을 중단해 계정 잠금 예방)
    if capture.get("videos", True):
        st = load_state()
        if st.get("login_disabled") and not manual:
            log("로그인 자동 실행이 중단된 상태입니다(이전 실패). 영상 스크래핑 건너뜀. "
                "웹의 [eCampus 지금 확인]으로 재시도하세요.")
        else:
            try:
                password = get_password(cfg)
                log("로그인 시도 (Playwright)…")
                cookies = ecampus.login_get_cookies(cfg["base_url"], cfg["login_id"], password)
                session = ecampus.make_session(cfg["base_url"], cookies)
                if not ecampus.verify_session(session, cfg["base_url"]):
                    raise RuntimeError("세션 검증 실패 — 아이디/비밀번호를 확인하세요.")
                log("로그인 성공")
                # 성공 시 중단 상태 해제
                if st.get("login_disabled"):
                    def _clear(s):
                        s["login_disabled"] = False
                        s["login_error"] = ""
                    mutate_state(_clear)
                    log("로그인 복구됨 — 자동 실행을 재개합니다.")

                courses = ecampus.get_courses(session, cfg["base_url"])
                log(f"강좌 {len(courses)}개 발견: " + ", ".join(courses.keys()))
                for cid in courses:
                    try:
                        vids = ecampus.scrape_course_videos(
                            session, cfg["base_url"], cid,
                            cfg.get("video_modtypes", ["xncommons", "vod"]),
                        )
                        candidates += vids
                        if vids:
                            log(f"  강좌 {cid}: 영상 수강기한 {len(vids)}건")
                    except Exception as e:  # noqa: BLE001
                        log(f"  강좌 {cid} 스크래핑 오류: {e}")
            except (SystemExit, Exception) as e:  # noqa: BLE001
                # 로그인/자격증명 실패 → 자동 실행 중단 플래그 설정 + 알림 (반복 시도 안 함)
                msg = str(e)[:300]
                def _disable(s):
                    s["login_disabled"] = True
                    s["login_error"] = msg
                mutate_state(_disable)
                log("로그인 실패로 자동 실행을 중단합니다: " + str(e).splitlines()[0])
                notify("eCampus 로그인 실패",
                       "자동 실행을 멈췄어요. 비밀번호 확인 후(setup.sh) 웹에서 재시도하세요.")

    # 2) 과제/일정 — ICS (로그인 불필요)
    ics_items = ecampus.fetch_ics(cfg["ics_url"])
    kept, dropped = [], 0
    for it in ics_items:
        if it["type"] == "assign" and capture.get("assignments", True):
            kept.append(it)
        elif it["type"] in ("event", "quiz") and capture.get("events", False):
            kept.append(it)
        else:
            dropped += 1
    candidates += kept
    log(f"ICS 이벤트 {len(ics_items)}건 → 채택 {len(kept)}건, 제외 {dropped}건")

    # 3) lookahead 필터
    days = cfg.get("lookahead_days", 0)
    if days and days > 0:
        now = datetime.now(KST)
        limit = now.timestamp() + days * 86400
        before = len(candidates)
        candidates = [c for c in candidates if c["due"] and c["due"].timestamp() <= limit]
        if before != len(candidates):
            log(f"lookahead {days}일 필터: {before} → {len(candidates)}건")

    return candidates


def serialize(c: dict) -> dict:
    """pending.json 저장용 (datetime → 문자열)."""
    out = dict(c)
    out["due"] = c["due"].strftime("%Y-%m-%d %H:%M") if c["due"] else ""
    out["due_iso"] = c["due"].isoformat() if c["due"] else ""
    return out


def main() -> int:
    cfg = load_config()
    manual = "--manual" in sys.argv
    try:
        candidates = gather_candidates(cfg, manual=manual)
    except Exception as e:  # noqa: BLE001
        log("수집 실패: " + str(e))
        log(traceback.format_exc())
        notify("eCampus 동기화 오류", str(e)[:120])
        return 1

    state = load_state()
    added = set(state["added"])
    subs = set(state["subscriptions"])
    seen = set(state["seen"])

    candidates.sort(key=lambda c: (c["due"] or datetime.max.replace(tzinfo=KST)))

    # 전체 카탈로그 저장 (웹 UI가 강좌별로 그룹핑)
    save_pending([serialize(c) for c in candidates])

    # 구독한 강좌의 미등록 항목은 자동으로 캘린더에 추가
    auto_added = []
    for c in candidates:
        if course_key(c) in subs and c["uid"] not in added:
            try:
                if add_candidate(cfg, serialize(c)):
                    added.add(c["uid"])
                    auto_added.append(c)
                    log(f"  자동 등록: [{c['type_label']}] {c['title']}")
            except Exception as e:  # noqa: BLE001
                log(f"  자동 등록 실패({c['title']}): {e}")

    # 미구독 강좌의 새 항목 (구독 유도용)
    unsub_new = [c for c in candidates
                 if course_key(c) not in subs and c["uid"] not in added and c["uid"] not in seen]

    # 잠금 아래 병합 저장 (동시 실행 시 덮어쓰기 방지)
    new_added = {c["uid"] for c in auto_added}
    all_uids = {c["uid"] for c in candidates}

    def _apply(s):
        s["added"] = sorted(set(s["added"]) | new_added)
        s["seen"] = sorted(set(s["seen"]) | all_uids)
    mutate_state(_apply)

    log(f"카탈로그 {len(candidates)}건 · 자동 등록 {len(auto_added)}건 · 미구독 새 항목 {len(unsub_new)}건")

    if auto_added:
        preview = ", ".join(c["title"] for c in auto_added[:3])
        more = f" 외 {len(auto_added) - 3}건" if len(auto_added) > 3 else ""
        notify("eCampus 자동 등록", f"{len(auto_added)}건 캘린더 추가: {preview}{more}")
    if unsub_new:
        courses = sorted({course_key(c) for c in unsub_new})
        clist = ", ".join(courses[:3]) + (" 외" if len(courses) > 3 else "")
        notify("eCampus 새 강좌/일정",
               f"미구독 {len(unsub_new)}건 ({clist})\n검토 페이지에서 강좌를 구독하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

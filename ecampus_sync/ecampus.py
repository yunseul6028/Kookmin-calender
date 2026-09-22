"""eCampus 접속·수집 로직.

- Playwright 로 MagicSSO 로그인 → 세션 쿠키 획득
- requests 세션으로 대시보드/강좌 페이지/ICS 조회
- 영상 수강기한(스크래핑) + 과제·일정(ICS) 을 후보 목록으로 정규화
"""
from __future__ import annotations

import html as html_mod
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")

# 한국어 라벨
TYPE_LABELS = {
    "video": "영상 수강",
    "assign": "과제",
    "quiz": "퀴즈/시험",
    "event": "일정",
}


# --------------------------------------------------------------------------- #
# 로그인 (Playwright)
# --------------------------------------------------------------------------- #
def login_get_cookies(base_url: str, login_id: str, password: str, *, headless: bool = True) -> dict:
    """MagicSSO 로그인 후 쿠키 dict(name->value) 반환. 실패 시 RuntimeError."""
    from playwright.sync_api import sync_playwright

    login_url = base_url.rstrip("/") + "/login/index.php"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

        page.fill('input[name="loginId"]', login_id)
        page.fill('input[name="loginPwd"]', password)
        # 로그인 폼 내부의 제출 버튼 (name="loginbutton"). 없으면 Enter 로 제출.
        btn = page.query_selector('form.loginform button[name="loginbutton"]') \
            or page.query_selector('form.loginform button[type="submit"]')
        if btn:
            btn.click()
        else:
            page.press('input[name="loginPwd"]', "Enter")

        # 로그인 후 /login/ 을 벗어날 때까지 대기 (SSO 리다이렉트 포함)
        try:
            page.wait_for_url(lambda u: "/login/index.php" not in u, timeout=30000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        final_url = page.url
        page_text = page.inner_text("body")[:500] if page.query_selector("body") else ""
        browser.close()

    if "MoodleSession" not in cookies:
        raise RuntimeError(
            "로그인 실패로 보입니다 (MoodleSession 쿠키 없음).\n"
            f"최종 URL: {final_url}\n페이지 일부: {page_text!r}"
        )
    return cookies


def make_session(base_url: str, cookies: dict) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh) ecampus-sync"
    host = re.sub(r"^https?://", "", base_url).split("/")[0]
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=host)
    return s


def verify_session(session: requests.Session, base_url: str) -> bool:
    """세션이 살아있는지 확인 (로그인 페이지로 튕기면 False)."""
    r = session.get(base_url.rstrip("/") + "/", timeout=30, allow_redirects=True)
    return "login/index.php" not in r.url and 'name="loginPwd"' not in r.text


# --------------------------------------------------------------------------- #
# 강좌 목록 + 영상 수강기한 스크래핑
# --------------------------------------------------------------------------- #
def get_courses(session: requests.Session, base_url: str) -> dict:
    """대시보드에서 {course_id: raw_name} 수집."""
    r = session.get(base_url.rstrip("/") + "/", timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    courses: dict[str, str] = {}
    for a in soup.select('a[href*="course/view.php?id="]'):
        m = re.search(r"course/view\.php\?id=(\d+)", a.get("href", ""))
        if not m:
            continue
        cid = m.group(1)
        name = re.sub(r"\s+", " ", a.get_text()).strip()
        if cid not in courses and name:
            courses[cid] = name
    return courses


def scrape_course_videos(session: requests.Session, base_url: str, course_id: str,
                         video_modtypes: list[str]) -> list[dict]:
    """강좌 페이지에서 영상/온라인콘텐츠의 수강기한(종료일)을 후보로 추출."""
    url = f"{base_url.rstrip('/')}/course/view.php?id={course_id}"
    r = session.get(url, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    # 강좌명 (깔끔한 이름) — <title> 또는 헤더
    course_name = None
    h = soup.select_one(".page-header-headings h1, h1.h2, .coursename")
    if h:
        course_name = re.sub(r"\s+", " ", h.get_text()).strip()
    if not course_name and soup.title:
        course_name = soup.title.get_text().split(":")[-1].strip()
    course_name = course_name or f"강좌 {course_id}"

    out: list[dict] = []
    seen_modules: set[str] = set()  # 같은 활동이 페이지에 여러 번 렌더링돼도 1회만
    for li in soup.select("li.activity"):
        classes = li.get("class", [])
        modtype = next((c[len("modtype_"):] for c in classes if c.startswith("modtype_")), None)
        if modtype not in video_modtypes:
            continue
        mid = (li.get("id") or "").replace("module-", "")
        if mid and mid in seen_modules:
            continue
        span = li.select_one("span.text-time")
        if not span:
            continue
        m = re.search(r"~\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", span.get_text())
        if not m:
            continue
        due_local = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)

        name_el = li.select_one(".instancename")
        title = re.sub(r"\s+", " ", name_el.get_text()).strip() if name_el else "(제목 없음)"
        # 뒤에 붙는 유형 라벨 정리
        title = re.sub(r"\s*동영상\(KCMS\)\s*$", "", title).strip()

        module_id = mid or title
        link_el = li.select_one("a[href]")
        link = link_el.get("href") if link_el else url

        seen_modules.add(module_id)
        out.append({
            "uid": f"video-{course_id}-{module_id}",
            "type": "video",
            "type_label": TYPE_LABELS["video"],
            "course": course_name,
            "title": title,
            "due": due_local,
            "url": link,
            "source": "scrape",
        })
    return out


# --------------------------------------------------------------------------- #
# ICS (과제·일정)
# --------------------------------------------------------------------------- #
def _unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _ics_unescape(v: str) -> str:
    v = v.replace("\\n", "\n").replace("\\N", "\n")
    v = v.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    return html_mod.unescape(v)


def _parse_ics_dt(name_params: str, value: str):
    """DTSTART/DTEND 값을 KST datetime 으로. (all-day 는 date, 시각 없음)."""
    is_date = "VALUE=DATE" in name_params and "VALUE=DATE-TIME" not in name_params
    if is_date or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=KST), True  # all-day
    m = re.match(r"(\d{8}T\d{6})(Z)?", value)
    if not m:
        return None, False
    dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")
    if m.group(2) == "Z":
        dt = dt.replace(tzinfo=timezone.utc).astimezone(KST)
    else:
        # TZID 가 있거나 없으면 현지(KST)로 간주
        dt = dt.replace(tzinfo=KST)
    return dt, False


def _classify_ics(description: str, summary: str) -> str:
    # Moodle 캘린더 이벤트는 SUMMARY 끝에 영어 접미사로 유형을 표시한다:
    #   "... is due"  = 과제/제출 마감,  "... closes" = 퀴즈·설문 마감,  "... opens" = 열림(마감 아님)
    d = (description or "").lower()
    s = (summary or "").strip()
    sl = s.lower()
    if "mod/assign" in d or sl.endswith("is due") or s.endswith("마감"):
        return "assign"
    if "mod/quiz" in d or sl.endswith("closes"):
        return "quiz"
    # "opens" 및 접미사 없는 일반 공지는 event 로 (마감이 아님)
    return "event"


def parse_ics(ics_text: str) -> list[dict]:
    lines = _unfold_ics(ics_text)
    events: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = key.split(";")[0].upper()
        if name in ("DTSTART", "DTEND"):
            dt, allday = _parse_ics_dt(key, value)
            cur[name] = dt
            cur[name + "_ALLDAY"] = allday
        elif name in ("SUMMARY", "UID", "DESCRIPTION", "CATEGORIES"):
            cur[name] = _ics_unescape(value)

    out: list[dict] = []
    for ev in events:
        due = ev.get("DTSTART") or ev.get("DTEND")
        if due is None:
            continue
        summary = ev.get("SUMMARY", "(제목 없음)")
        etype = _classify_ics(ev.get("DESCRIPTION", ""), summary)
        # Moodle 접미사(is due/closes/opens) 제거해 제목 깔끔하게
        title = re.sub(r"\s*(is due|closes|opens)\s*$", "", summary.strip(), flags=re.I).strip()
        out.append({
            "uid": "ics-" + ev.get("UID", summary + str(due)),
            "type": etype,
            "type_label": TYPE_LABELS.get(etype, "일정"),
            "course": ev.get("CATEGORIES", ""),
            "title": title or summary,
            "due": due,
            "allday": ev.get("DTSTART_ALLDAY", False),
            "url": "",
            "source": "ics",
        })
    return out


def fetch_ics(ics_url: str) -> list[dict]:
    """ICS 는 토큰 URL 이라 로그인 없이 조회 가능."""
    r = requests.get(ics_url, timeout=30)
    r.raise_for_status()
    return parse_ics(r.text)

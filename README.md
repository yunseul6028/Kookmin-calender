# 국민대 eCampus → 맥 캘린더 동기화 에이전트

국민대 eCampus(Moodle/coursemos)에서 **과제 마감일**과 **온라인 강의 수강 기한**을
자동으로 모아, **구독한 강좌의 일정은 자동으로** 맥 기본 캘린더에 넣어주는 도구.

## 동작 방식 — 강좌 구독 모델

강좌(수업)별로 **구독 ON** 한 번만 하면, 그 강좌의 **모든 일정(현재 + 앞으로 생기는 것)이
자동으로** 캘린더에 등록됩니다. 매번 고를 필요 없음.

```
[매일 자동 · launchd]                              [처음 한 번 · 웹 UI]
 fetch  ─ eCampus 로그인(영상 기한 스크래핑)          강좌별 구독 토글 ON/OFF
        └ ICS 조회(과제·일정)                        (구독 켜면 그 강좌 일정
        └ 구독 강좌 새 항목 → 캘린더 자동 등록 ✅         전부 자동 등록)
        └ 미구독 강좌 새 항목 → "구독?" 맥 알림 🔔
```

설정은 **로컬 웹페이지**(http://127.0.0.1:8765)에서 합니다. 웹서버는 launchd로
항상 켜져 있으니, **`eCampus 검토.webloc` 파일을 더블클릭**(또는 북마크)하면 바로 열려요.

- **탐지는 자동**, **캘린더 등록은 내 승인 후** — "매번 확인하고 선택" 요구를 만족.
- 데이터 소스 2개:
  - 과제·일정 → Moodle **ICS 내보내기 토큰 URL** (로그인 불필요)
  - 영상 수강 기한 → 강좌 페이지 스크래핑 (**로그인 필요**, Playwright + 키체인)

## 설치

```bash
cd ~/Claude/Kookmin-calender
# 1) config.json 의 login_id 를 본인 포털 통합ID로 수정
# 2) 의존성 설치 + 키체인에 비밀번호 저장(입력창은 가려짐)
./setup.sh
# 3) 매일 자동 실행 등록
./install_launchd.sh
```

## 사용

터미널 필요 없음. **`eCampus 검토.webloc` 더블클릭** → 웹페이지에서:
- 강좌 카드의 **구독 토글 ON** → 그 강좌의 현재 일정 즉시 등록 + 이후 자동 등록
- **구독 OFF** → 이후 자동 등록 중단 (이미 등록된 캘린더 일정은 그대로 유지)
- **[🔄 eCampus 지금 확인]** → 즉시 다시 수집 (평소엔 launchd가 매일 자동)

구독한 강좌에 새 일정이 생기면 다음 수집 때 **자동 등록**되고, 미구독 강좌에
새 일정이 생기면 "구독하시겠어요?" **맥 알림**이 옵니다.

## 수동 실행 (선택)

```bash
python3 -m ecampus_sync.webapp   # 웹 UI 직접 실행 (평소엔 launchd가 상주)
python3 -m ecampus_sync.fetch    # 수집 + 구독 강좌 자동 등록 한 번
```

## 설정 (config.json)

| 키 | 설명 |
|---|---|
| `ics_url` | 캘린더>내보내기>'일정 URL 불러오기'로 만든 개인 토큰 주소 (외부 노출 금지) |
| `login_id` | 포털 통합ID |
| `calendar_name` | 넣을 캘린더 이름. **iCloud에 이 이름의 캘린더가 미리 있어야 함**(없으면 안내 후 중단). AppleScript로 iCloud 캘린더 생성이 안 되므로 Calendar 앱에서 직접 생성 |
| `capture` | 가져올 종류: `assignments`/`videos`/`events` |
| `reminder_minutes` | 마감 몇 분 전 알림 (1440 = 하루 전) |
| `lookahead_days` | N일 이내 마감만 (0=제한 없음) |

## 파일

- `ecampus_sync/ecampus.py` — 로그인·스크래핑·ICS 파싱
- `ecampus_sync/fetch.py` — 수집기(자동 실행 대상)
- `ecampus_sync/webapp.py` — 검토 웹 UI(상주 서버)
- `ecampus_sync/review.py` — 검토·캘린더 추가(터미널 버전)
- `ecampus_sync/calendar_mac.py` — AppleScript 캘린더 연동
- `eCampus 검토.webloc` — 검토 페이지 바로가기(더블클릭)
- `state.json` — 구독 강좌 / 추가한 항목 / 본 항목 (중복 방지)
- `pending.json` — 현재 수집된 전체 일정 카탈로그(웹 UI가 강좌별로 그룹핑)
- `sync.log`, `launchd.log` — 로그

## 보안 메모

- 비밀번호는 **macOS 키체인**에만 저장됩니다. 코드/설정 파일엔 없습니다.
- `setup.sh` 는 완전 자동 실행을 위해 `-A`(모든 앱 접근 허용)로 저장합니다.
  더 엄격하게 하려면 `-A` 대신 `-T /usr/bin/security` 로 다시 저장하세요.
- `config.json` 의 `ics_url` 에는 개인 토큰이 있으니 공유 금지. (`.gitignore` 처리됨)
- 토큰을 무효화하려면 eCampus 캘린더 내보내기 화면에서 재발급하세요.

## 문제 해결

- 로그인 실패: `sync.log` 확인. 세션 만료/비번 변경 시 `./setup.sh` 로 비번 갱신.
- 캘린더 권한: 첫 실행 시 "캘린더 제어 허용" 창이 뜨면 허용.
- launchd 로그: `launchd.log`.

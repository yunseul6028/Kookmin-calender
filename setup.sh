#!/bin/bash
# eCampus 동기화 에이전트 초기 설정
set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
PY="$(which python3)"

echo "=== eCampus 동기화 설정 ==="
echo "프로젝트: $PROJECT_DIR"
echo "python3 : $PY"
echo

# 1) 의존성
echo "[1/3] 파이썬 패키지 설치…"
"$PY" -m pip install -q -r requirements.txt
"$PY" -m playwright install chromium >/dev/null 2>&1 || true
echo "  완료."
echo

# 2) config.json 확인
if [ ! -f config.json ]; then
  echo "config.json 이 없습니다. config.example.json 을 복사해 만드세요."
  exit 1
fi
LOGIN_ID=$("$PY" -c "import json;print(json.load(open('config.json'))['login_id'])")
SERVICE=$("$PY" -c "import json;print(json.load(open('config.json'))['keychain_service'])")
if [ "$LOGIN_ID" = "YOUR_PORTAL_ID" ] || [ -z "$LOGIN_ID" ]; then
  echo "먼저 config.json 의 \"login_id\" 를 본인 포털 통합ID 로 바꾸세요."
  exit 1
fi

# 3) 키체인에 비밀번호 저장 (입력값은 화면에 안 보이며, 이 스크립트/Claude 는 값을 못 봄)
echo "[2/3] 포털 비밀번호를 macOS 키체인에 저장합니다."
echo "  서비스='$SERVICE'  계정='$LOGIN_ID'"
echo "  (비밀번호 입력창이 뜹니다. 완전 자동 실행을 위해 -A 옵션으로 저장합니다.)"
security add-generic-password -s "$SERVICE" -a "$LOGIN_ID" -U -A -w
echo "  저장 완료."
echo

echo "[3/3] 설정 끝!"
echo
echo "다음 명령으로 수집을 테스트하세요:"
echo "  $PY -m ecampus_sync.fetch"
echo "그다음 검토·추가:"
echo "  $PY -m ecampus_sync.review"
echo
echo "매일 자동 실행하려면:"
echo "  ./install_launchd.sh"

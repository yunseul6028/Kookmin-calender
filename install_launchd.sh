#!/bin/bash
# 자동화 설치:
#   1) 수집기(fetch)  - 매일 08:30, 18:30 자동 실행
#   2) 검토 웹서버     - 항상 켜둠(127.0.0.1:8765), 재부팅/크래시 시 자동 재시작
set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
PY="$(which python3)"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"

# --- 1) 수집기 (스케줄) ---
FETCH="com.kookmin.ecampus-sync"
cat > "$LA/$FETCH.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$FETCH</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>-m</string><string>ecampus_sync.fetch</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <!-- 하루 1회(08:30). 학교 계정에 부담을 최소화. -->
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$PROJECT_DIR/launchd.log</string>
  <key>StandardErrorPath</key><string>$PROJECT_DIR/launchd.log</string>
</dict></plist>
EOF

# --- 2) 검토 웹서버 (상주) ---
WEB="com.kookmin.ecampus-web"
cat > "$LA/$WEB.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$WEB</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>-m</string><string>ecampus_sync.webapp</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PROJECT_DIR/web.log</string>
  <key>StandardErrorPath</key><string>$PROJECT_DIR/web.log</string>
  <key>EnvironmentVariables</key><dict><key>ECAMPUS_NO_BROWSER</key><string>1</string></dict>
</dict></plist>
EOF

for L in "$FETCH" "$WEB"; do
  launchctl unload "$LA/$L.plist" 2>/dev/null || true
  launchctl load "$LA/$L.plist"
done

echo "설치 완료:"
echo "  · 수집기  $FETCH  (매일 08:30, 1회)"
echo "  · 웹서버  $WEB     (상주, http://127.0.0.1:8765 )"
echo
echo "검토 페이지: http://127.0.0.1:8765  ('eCampus 검토.webloc' 더블클릭)"
echo "해제:  launchctl unload $LA/$FETCH.plist $LA/$WEB.plist && rm $LA/$FETCH.plist $LA/$WEB.plist"

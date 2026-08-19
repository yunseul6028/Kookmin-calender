"""설정 로드 + macOS 키체인에서 비밀번호 읽기."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

# 프로젝트 루트 (이 파일: <root>/ecampus_sync/config.py)
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
PENDING_PATH = ROOT / "pending.json"
LOG_PATH = ROOT / "sync.log"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"설정 파일이 없습니다: {CONFIG_PATH}\n"
            "config.example.json 을 복사해 config.json 을 만들고 값을 채우세요."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        # "//..." 로 시작하는 주석성 키는 무시
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("//")}


def get_password(cfg: dict) -> str:
    """키체인에서 포털 비밀번호를 읽는다. security CLI를 통해 접근."""
    service = cfg["keychain_service"]
    # 키체인 계정명. 지정 없으면 login_id 사용.
    account = cfg.get("keychain_account") or cfg["login_id"]
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "키체인에서 비밀번호를 찾지 못했습니다.\n"
            "setup.sh 를 실행하거나 아래 명령으로 저장하세요:\n"
            f'  security add-generic-password -s "{service}" -a "{account}" -w -U -A'
        )
    return out.stdout.rstrip("\n")

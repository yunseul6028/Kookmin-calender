"""검토/구독용 얇은 로컬 웹 UI.

강좌(수업)별로 그룹을 보여주고, '구독' 토글을 켜면 그 강좌의 모든 일정이
(현재 것 즉시 + 앞으로 생기는 것은 수집 때 자동으로) 캘린더에 등록된다.
추가 의존성 없음(표준 라이브러리).

실행:  python3 -m ecampus_sync.webapp
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import load_config
from .events import add_candidate, course_key
from .store import load_pending, load_state, mutate_state

HOST, PORT = "127.0.0.1", 8765

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eCampus 강좌 구독</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--line:#e5e7eb;--txt:#1f2430;--sub:#6b7280;--accent:#2b6cb0;--ok:#2e7d46;}
@media(prefers-color-scheme:dark){:root{--bg:#12141a;--card:#1b1e26;--line:#2c313c;--txt:#e6e8ee;--sub:#9aa2b1;--accent:#4b8fd6;--ok:#5bbd7a;}}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;background:var(--bg);color:var(--txt)}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:14px 20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;z-index:5}
h1{font-size:17px;margin:0;font-weight:700}
.spacer{flex:1}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--txt);border-radius:9px;padding:8px 13px;cursor:pointer}
button:hover{border-color:var(--accent)}
button:disabled{opacity:.5;cursor:default}
main{max-width:820px;margin:0 auto;padding:16px 16px 60px}
.meta{color:var(--sub);font-size:13px;padding:4px 2px 12px}
.group{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:14px;overflow:hidden}
.group.sub{border-color:var(--ok)}
.ghead{display:flex;align-items:center;gap:12px;padding:14px 16px}
.gtitle{font-weight:700;font-size:15.5px;flex:1;min-width:0}
.gnote{font-size:12.5px;color:var(--sub);margin-top:3px;font-weight:400}
.gnote.on{color:var(--ok);font-weight:600}
.items{border-top:1px dashed var(--line);padding:6px 16px 12px}
.item{display:flex;gap:10px;align-items:baseline;padding:7px 0;border-bottom:1px solid transparent}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;flex:none}
.b-video{background:#e6f0fb;color:#1a4e82}.b-assign{background:#fdeaea;color:#a12626}
.b-quiz{background:#fef3e0;color:#9a5b0a}.b-event{background:#e9eef2;color:#40566b}
@media(prefers-color-scheme:dark){.b-video{background:#22364d;color:#9cc4ee}.b-assign{background:#4a2626;color:#f0a3a3}.b-quiz{background:#463316;color:#f0c489}.b-event{background:#2a3340;color:#aebccb}}
.it-body{flex:1;min-width:0}
.it-title{font-size:14px}
.it-sub{font-size:12.5px;color:var(--sub);margin-top:1px}
.dday{font-weight:700}.dday.soon{color:#c0392b}.dday.over{color:#9aa2b1}
.tag-added{font-size:11px;color:var(--ok);font-weight:700;flex:none}
.empty{text-align:center;color:var(--sub);padding:60px 0}
/* toggle switch */
.sw{position:relative;width:50px;height:28px;flex:none}
.sw input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#c7ccd6;border-radius:999px;transition:.2s;cursor:pointer}
.sl:before{content:"";position:absolute;height:22px;width:22px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s}
.sw input:checked + .sl{background:var(--ok)}
.sw input:checked + .sl:before{transform:translateX(22px)}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1f2430;color:#fff;padding:10px 16px;border-radius:10px;opacity:0;transition:.25s;pointer-events:none;font-size:14px}
#toast.show{opacity:.95}
</style></head>
<body>
<header>
  <h1>📚 eCampus 강좌 구독</h1>
  <span class="spacer"></span>
  <button id="refresh" onclick="refresh()">🔄 eCampus 지금 확인</button>
</header>
<main>
  <div class="meta">강좌의 <b>구독</b>을 켜면 그 강좌의 모든 일정이 자동으로 캘린더에 등록됩니다.</div>
  <div id="list"></div>
</main>
<div id="toast"></div>
<script>
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function dday(iso){if(!iso)return['',''];const d=new Date(iso),n=new Date();
  const days=Math.ceil((d-n)/86400000);
  if(days<0)return['지남 '+(-days)+'일','over'];
  if(days===0)return['오늘','soon'];
  return['D-'+days, days<=3?'soon':''];}
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400)}
async function load(){const r=await fetch('/api/groups');const j=await r.json();render(j.groups||[]);}
function render(groups){
  const L=document.getElementById('list');
  if(!groups.length){L.innerHTML='<div class="empty">아직 강좌가 없어요.<br>개강 후 또는 [eCampus 지금 확인]을 눌러보세요.</div>';return;}
  L.innerHTML=groups.map(g=>{
    const items=g.items.map(c=>{const[dd,cls]=dday(c.due_iso);
      return `<div class="item">
        <span class="badge b-${c.type}">${esc(c.type_label)}</span>
        <div class="it-body"><div class="it-title">${esc(c.title)}</div>
          <div class="it-sub">마감 ${esc(c.due||'?')} · <span class="dday ${cls}">${dd}</span></div></div>
        ${c.added?'<span class="tag-added">✓ 등록됨</span>':''}
      </div>`}).join('');
    return `<div class="group ${g.subscribed?'sub':''}">
      <div class="ghead">
        <div class="gtitle">${esc(g.course)}
          <div class="gnote ${g.subscribed?'on':''}">${g.subscribed
            ? '✅ 구독 중 — 새 일정이 자동 등록됩니다 ('+g.added+'/'+g.count+' 등록)'
            : '구독하면 이 강좌 일정('+g.count+'건)이 자동 등록됩니다'}</div>
        </div>
        <label class="sw"><input type="checkbox" ${g.subscribed?'checked':''}
           onchange="sub(this,'${encodeURIComponent(g.course)}')"><span class="sl"></span></label>
      </div>
      <div class="items">${items}</div>
    </div>`}).join('');
}
async function sub(el,courseEnc){el.disabled=true;
  const course=decodeURIComponent(courseEnc);
  const r=await fetch('/api/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({course,on:el.checked})});
  const j=await r.json();
  if(j.error){toast('오류: '+j.error);el.checked=!el.checked;el.disabled=false;return;}
  toast(el.checked?`구독 켬 — ${j.added}건 캘린더 추가`:'구독 끔');
  await load();
}
async function refresh(){const b=document.getElementById('refresh');b.disabled=true;b.textContent='확인 중…';
  try{const r=await fetch('/api/refresh',{method:'POST'});const j=await r.json();
    if(j.error)toast('수집 오류: '+j.error);
    else toast('확인 완료 — 자동 등록 '+j.auto+'건'+(j.unsub?(', 미구독 새 항목 '+j.unsub+'건'):''));
    await load();}
  finally{b.disabled=false;b.textContent='🔄 eCampus 지금 확인';}}
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html")
        elif self.path == "/api/groups":
            self._send(200, json.dumps(self._groups(), ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            if self.path == "/api/subscribe":
                b = self._json_body()
                self._send(200, json.dumps(self._subscribe(b.get("course", ""), bool(b.get("on")))))
            elif self.path == "/api/refresh":
                self._send(200, json.dumps(self._refresh()))
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:  # noqa: BLE001
            self._send(200, json.dumps({"error": str(e)}))

    # --- 로직 ---
    def _groups(self):
        catalog = load_pending()
        state = load_state()
        subs = set(state["subscriptions"])
        added = set(state["added"])
        by_course: dict[str, dict] = {}
        for c in catalog:
            key = course_key(c)
            g = by_course.setdefault(key, {"course": key, "subscribed": key in subs,
                                           "count": 0, "added": 0, "items": []})
            is_added = c["uid"] in added
            g["count"] += 1
            g["added"] += 1 if is_added else 0
            g["items"].append({
                "title": c["title"], "type": c["type"], "type_label": c["type_label"],
                "due": c.get("due", ""), "due_iso": c.get("due_iso", ""), "added": is_added,
            })
        # 미구독 먼저, 그다음 강좌명 순
        groups = sorted(by_course.values(), key=lambda g: (g["subscribed"], g["course"]))
        return {"groups": groups}

    def _subscribe(self, course: str, on: bool):
        course = (course or "").strip()
        if not course:
            return {"error": "강좌명이 비어 있습니다"}
        added_uids: set[str] = set()
        last_err = ""
        to_add = []
        if on:
            cfg = load_config()
            catalog = load_pending()
            already = set(load_state()["added"])
            _seen: set[str] = set()
            to_add = [c for c in catalog if course_key(c) == course
                      and c["uid"] not in already
                      and not (c["uid"] in _seen or _seen.add(c["uid"]))]
            for c in to_add:
                try:
                    if add_candidate(cfg, c):
                        added_uids.add(c["uid"])
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)

        # 넣을 항목이 있는데 하나도 못 넣었다면(예: 캘린더 없음) 구독을 켜지 않고 안내
        if on and to_add and not added_uids:
            return {"error": last_err or "캘린더에 추가하지 못했습니다"}

        def _apply(s):
            subs = set(s["subscriptions"])
            subs.add(course) if on else subs.discard(course)
            s["subscriptions"] = sorted(subs)
            if added_uids:
                s["added"] = sorted(set(s["added"]) | added_uids)
        mutate_state(_apply)
        return {"subscribed": on, "added": len(added_uids)}

    def _refresh(self):
        r = subprocess.run([sys.executable, "-m", "ecampus_sync.fetch", "--manual"],
                           capture_output=True, text=True)
        auto = unsub = 0
        for line in (r.stdout + r.stderr).splitlines():
            if "자동 등록" in line and "건 ·" in line:
                # "카탈로그 N건 · 자동 등록 X건 · 미구독 새 항목 Y건"
                import re
                m = re.search(r"자동 등록 (\d+)건 · 미구독 새 항목 (\d+)건", line)
                if m:
                    auto, unsub = int(m.group(1)), int(m.group(2))
        if r.returncode != 0:
            tail = (r.stdout + r.stderr).strip().splitlines()
            return {"error": (tail[-1] if tail else "수집 실패"), "auto": auto, "unsub": unsub}
        return {"auto": auto, "unsub": unsub}


def main() -> int:
    url = f"http://{HOST}:{PORT}/"
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"eCampus 구독 UI: {url}  (종료: Ctrl+C)")
    if not os.environ.get("ECAMPUS_NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

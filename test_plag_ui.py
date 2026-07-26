# 표절 오버레이 스모크 테스트 — GitHub API를 가로채 실제 지문 색인으로 화면을 띄우고
# 빨간 그라데이션이 정말 그려지는지 확인한다.
#   python test_plag_ui.py <_plag_index.json> [출력폴더]
import base64, json, sys, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
idx_p = Path(sys.argv[1])
outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "_plagtest"
outdir.mkdir(exist_ok=True)
index_json = idx_p.read_text(encoding="utf-8")

# 델리스파이스 「고백」 구절을 일부러 심은 가짜 곡 — 걸려야 정상
SONG = """# TEST 「검사곡」

**Style of Music:**
```
test style
```

## 가사

```
[Verse 1]
간판의 글자가 하나씩 뭉개져
네 넓은 가슴에 묻혀 다른 누구를 생각했었어
창에 비친 게 어젯밤의 나라서
```

## 추천안

```
[Verse 1]
네 넓은 가슴에 묻혀 다른 누구를 생각했었어
```

### 추천 근거
테스트용
"""

b64 = lambda s: base64.b64encode(s.encode()).decode()
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
Handler.log_message = lambda *a, **k: None
srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,PUT,OPTIONS"}

def handle(route, request):
    if request.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    u = request.url
    if "_plag_index.json" in u:
        # 앱이 raw 미디어 타입으로 받으므로(색인이 900KB라 base64는 1MB 한도 초과)
        # 실제 API 와 똑같이 원문을 그대로 돌려준다
        if "vnd.github.raw" in (request.headers.get("accept") or ""):
            return route.fulfill(status=200, headers=CORS,
                                 content_type="application/json", body=index_json)
        body = json.dumps({"sha": "s", "content": b64(index_json)})
    elif u.rstrip("/").endswith("contents/lyrics"):
        body = json.dumps([{"name": "A99_검사곡.md", "path": "lyrics/A99_검사곡.md", "type": "file"}])
    else:
        body = json.dumps({"sha": "s", "content": b64(SONG)})
    route.fulfill(status=200, headers=CORS, content_type="application/json", body=body)

fails = []
def check(c, label):
    print(("  [OK] " if c else "  [FAIL] ") + label)
    if not c: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script("localStorage.setItem('yein_tok','test-token')")
    ctx.route("**api.github.com/**", handle)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/index.html")
    pg.wait_for_selector("#songs button", timeout=15000)
    pg.click("#songs button")
    pg.wait_for_selector("#taLyrics", timeout=10000)
    pg.wait_for_timeout(6000)          # 지문 대조는 비동기(SHA-1)라 여유를 준다

    print("\n[1] 표절 오버레이")
    marks = pg.locator("#taBack mark")
    check(not errs, f"JS 에러 없음 {errs[:2]}")
    check(marks.count() > 0, f"편집칸에 하이라이트 생성됨 ({marks.count()}개)")
    if marks.count():
        txt = marks.first.inner_text()
        check("가슴에" in txt or "묻혀" in txt or "누구를" in txt, f"심어둔 표절 구절이 잡힘: 「{txt}」")
        bg = marks.first.evaluate("e=>getComputedStyle(e).backgroundImage")
        check("gradient" in bg, "빨간 그라데이션이 실제로 적용됨")
    check(pg.locator("#plagBar.show").count() == 1, "경고 배너 노출")
    if pg.locator("#plagBar").count():
        print("      배너:", pg.locator("#plagBar b").inner_text())

    print("\n[2] 무혐의 구절은 안 덮는가")
    all_marked = " ".join(marks.all_inner_texts())
    check("창에 비친" not in all_marked, "교체본(창에 비친 게 어젯밤의 나라서)은 하이라이트 없음")

    print("\n[3] 추천안 패널도 검사되는가")
    check(pg.locator("#propText mark").count() > 0,
          f"추천안 쪽 하이라이트 ({pg.locator('#propText mark').count()}개)")

    pg.screenshot(path=str(outdir / "1_표절오버레이.png"), full_page=False)
    pg.locator(".taWrap").screenshot(path=str(outdir / "2_편집칸.png"))
    check(not errs, f"끝까지 JS 에러 없음 {errs[:2]}")
    b.close()

srv.shutdown()
print(f"\n스크린샷: {outdir}")
print(f"결과: {'전부 통과' if not fails else str(len(fails))+'건 실패 → '+str(fails)}")
sys.exit(1 if fails else 0)

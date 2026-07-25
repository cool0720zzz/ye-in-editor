# 좌우 비교뷰 스모크 — 실제 곡 파일로 "왼쪽 기존 / 오른쪽 추천안 / 선택한 것만 남음" 확인
#   python test_compare_ui.py <곡.md> <_plag_index.json> [출력폴더]
import base64, json, sys, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
song = Path(sys.argv[1]).read_text(encoding="utf-8")
index_json = Path(sys.argv[2]).read_text(encoding="utf-8")
outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "_cmptest"
outdir.mkdir(exist_ok=True)

b64 = lambda s: base64.b64encode(s.encode()).decode()
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
Handler.log_message = lambda *a, **k: None
srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,PUT,OPTIONS"}
puts = []

def handle(route, request):
    if request.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    if request.method == "PUT":
        puts.append(json.loads(request.post_data))
        return route.fulfill(status=200, headers=CORS, content_type="application/json",
                             body=json.dumps({"content": {"sha": "s2"}}))
    u = request.url
    if "_plag_index.json" in u:
        body = json.dumps({"sha": "s", "content": b64(index_json)})
    elif u.rstrip("/").endswith("contents/lyrics"):
        body = json.dumps([{"name": "A04_번화가.md", "path": "lyrics/A04_번화가.md", "type": "file"}])
    else:
        body = json.dumps({"sha": "s", "content": b64(song)})
    route.fulfill(status=200, headers=CORS, content_type="application/json", body=body)

fails = []
def check(c, label):
    print(("  [OK] " if c else "  [FAIL] ") + label)
    if not c: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1400, "height": 1000})
    ctx.add_init_script("localStorage.setItem('yein_tok','test-token')")
    ctx.route("**api.github.com/**", handle)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/index.html")
    pg.wait_for_selector("#songs button", timeout=15000)

    print("\n[1] 제목 클릭 → 좌우 비교뷰")
    pg.click("#songs button")
    pg.wait_for_selector("#taLyrics", timeout=10000)
    pg.wait_for_timeout(2000)
    check(not errs, f"JS 에러 없음 {errs[:2]}")
    check(pg.locator("#cmp.two").count() == 1, "2단 레이아웃 활성")
    check(pg.locator("#paneProp:not(.hide)").count() == 1, "우측 추천안 패널 노출")
    before = pg.locator("#taLyrics").input_value()
    prop = pg.locator("#propText").inner_text()
    check(before.strip() != prop.strip(), "좌(기존) 와 우(추천안) 내용이 다름")
    check("아무도 내 이름을 안 불러" in prop, "추천안에 제안 구절이 보임")
    check("아무도 내 이름을 안 불러" not in before, "기존 가사는 아직 안 바뀜")
    check(pg.locator("#propWhy").count() == 1, "추천 근거 접이식 노출")
    pg.screenshot(path=str(outdir / "1_좌우비교.png"), full_page=False)

    print("\n[2] 적용 안 하면 기존 가사가 남는가")
    check(pg.locator("#dirty.hide").count() == 1, "수정 표시 없음 (건드리지 않았으므로)")
    check(len(puts) == 0, "깃허브에 아무것도 안 보냄")

    print("\n[3] [적용] → [확정] 해야 내 선택이 저장되는가")
    pg.once("dialog", lambda d: d.accept())
    pg.click("#btnApply")
    pg.wait_for_timeout(600)
    after = pg.locator("#taLyrics").input_value()
    check("아무도 내 이름을 안 불러" in after, "적용 후 왼쪽이 추천안으로 바뀜")
    check(len(puts) == 0, "아직 저장 안 됨 — [확정] 전")
    pg.screenshot(path=str(outdir / "2_적용후.png"), full_page=False)
    pg.click("#btnCommit")
    pg.wait_for_timeout(1500)
    check(len(puts) == 1, "[확정] 눌러야 깃허브에 반영")
    if puts:
        saved = base64.b64decode(puts[0]["content"]).decode()
        check("아무도 내 이름을 안 불러" in saved, "선택한 가사가 저장됨")
        check("## 추천안" in saved, "추천안 섹션은 파일에 그대로 보존")
    check(not errs, f"끝까지 JS 에러 없음 {errs[:2]}")
    b.close()

srv.shutdown()
print(f"\n스크린샷: {outdir}")
print(f"결과: {'전부 통과' if not fails else str(len(fails))+'건 실패 → '+str(fails)}")
sys.exit(1 if fails else 0)

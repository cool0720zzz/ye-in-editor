# 곡 지도(3축 산점도) 스모크 — 점이 그려지고, 돌아가고, 눌러서 정보가 뜨는지
#   python test_map_ui.py <_map.json> [출력폴더]
import base64, json, sys, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
MAP_RAW = Path(sys.argv[1]).read_text(encoding="utf-8")
MAP = json.loads(MAP_RAW)
outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "_maptest"
outdir.mkdir(exist_ok=True)
N = len(MAP["songs"])

b64 = lambda s: base64.b64encode(s.encode()).decode()
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
Handler.log_message = lambda *a, **k: None
srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}

def handle(route, request):
    u = request.url
    if "_map.json" in u:
        if "vnd.github.raw" in (request.headers.get("accept") or ""):
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=MAP_RAW)
        body = json.dumps({"sha": "s", "content": b64(MAP_RAW)})
    elif u.rstrip("/").endswith("contents/lyrics"):
        body = json.dumps([{"name": "A01_네온.md", "path": "lyrics/A01_네온.md", "type": "file"}])
    else:
        body = json.dumps({"sha": "s", "content": b64("## 가사\n\n```\n[Verse]\n테스트\n```\n")})
    route.fulfill(status=200, headers=CORS, content_type="application/json", body=body)

fails = []
def check(c, label):
    print(("  [OK] " if c else "  [FAIL] ") + label)
    if not c: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 430, "height": 1000})
    ctx.add_init_script("localStorage.setItem('yein_tok','test-token')")
    ctx.route("**api.github.com/**", handle)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
    pg.wait_for_selector("#btnMap", timeout=15000)

    print("\n[1] 지도가 그려지는가")
    pg.click("#btnMap")
    pg.wait_for_selector("#mapSvg .mapdot", timeout=10000)
    pg.wait_for_timeout(500)
    check(not errs, f"JS 에러 없음 {errs[:2]}")
    check(pg.locator("#mapSvg .mapdot").count() == N, f"점 {N}개 (실제 {pg.locator('#mapSvg .mapdot').count()})")
    # SVG <text> 는 innerText 가 안 잡힌다 — textContent 로 읽어야 한다
    labels = [t.strip() for t in pg.locator("#mapSvg text").all_text_contents()]
    for ax in ("BPM", "밝기", "시선"):
        check(ax in labels, f"축 라벨 '{ax}'")
    titles = {s["title"] for s in MAP["songs"]}
    shown = [t for t in labels if t in titles]
    check(len(shown) >= 5, f"곡 라벨이 최소 5개는 보임 (실제 {len(shown)}개)")
    # 라벨이 서로 겹치면 아무것도 못 읽는다 — 실제 렌더 박스로 확인
    boxes = pg.evaluate("""(titles) => [...document.querySelectorAll('#mapSvg text')]
        .filter(t => titles.includes(t.textContent.trim()))
        .map(t => { const b = t.getBBox(); return {x:b.x, y:b.y, w:b.width, h:b.height}; })""",
        list(titles))
    over = [(i, j) for i in range(len(boxes)) for j in range(i+1, len(boxes))
            if boxes[i]["x"] < boxes[j]["x"]+boxes[j]["w"] and boxes[i]["x"]+boxes[i]["w"] > boxes[j]["x"]
            and boxes[i]["y"] < boxes[j]["y"]+boxes[j]["h"] and boxes[i]["y"]+boxes[i]["h"] > boxes[j]["y"]]
    check(not over, f"곡 라벨끼리 안 겹침 (겹친 쌍 {len(over)})")
    check(pg.locator("#mapSvg line").count() >= 12, "정육면체 뼈대가 그려짐")
    pg.screenshot(path=str(outdir / "1_지도.png"), full_page=False)

    print("\n[2] 드래그하면 실제로 돌아가는가")
    before = pg.locator("#mapSvg .mapdot circle").first.get_attribute("cx")
    box = pg.locator("#mapSvg").bounding_box()
    pg.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
    pg.mouse.down(); pg.mouse.move(box["x"] + box["width"]/2 + 90, box["y"] + box["height"]/2 + 30, steps=8)
    pg.mouse.up(); pg.wait_for_timeout(300)
    after = pg.locator("#mapSvg .mapdot circle").first.get_attribute("cx")
    check(before != after, f"회전 후 좌표가 바뀜 ({before} → {after})")
    pg.screenshot(path=str(outdir / "2_회전후.png"), full_page=False)

    print("\n[3] 각도 초기화")
    pg.click("#btnMapReset"); pg.wait_for_timeout(300)
    check(pg.locator("#mapSvg .mapdot circle").first.get_attribute("cx") == before, "초기화하면 원래 각도로")

    print("\n[4] 점을 누르면 곡 정보가 뜨는가")
    check(pg.locator("#mapInfo.hide").count() == 1, "처음엔 정보 카드가 숨어 있음")
    target = pg.locator('#mapSvg .mapdot[data-id="A05"]')
    check(target.count() == 1, "세 시간(A05) 점이 있음")
    target.click(); pg.wait_for_timeout(300)
    info = pg.locator("#mapInfo").inner_text()
    s5 = next(x for x in MAP["songs"] if x["id"] == "A05")
    check(pg.locator("#mapInfo.hide").count() == 0, "정보 카드가 열림")
    check(s5["title"] in info, "제목 표시")
    check(str(s5["bpm"]) in info, "BPM 표시")
    check(s5["emotion"] in info, "정서 표시")
    check(s5["close"] in info, "곡을 닫는 말 표시")
    # 겹쳐서 숨겨졌더라도 '선택한 곡'의 라벨은 반드시 살아 있어야 한다
    sel = [t.strip() for t in pg.locator("#mapSvg text").all_text_contents()]
    check(s5["title"] in sel, "선택한 곡 라벨은 겹쳐도 항상 표시")
    pg.screenshot(path=str(outdir / "3_점선택.png"), full_page=False)

    print("\n[5] 표도 같이 나오는가")
    check(pg.locator("#mapTable tbody tr").count() == N, f"표 {N}행")
    first_bpm = pg.locator("#mapTable tbody tr td:nth-child(2)").first.inner_text()
    check(str(min(s["bpm"] for s in MAP["songs"])) in first_bpm, "느린 곡부터 정렬")

    print("\n[6] 목록으로 돌아가기")
    pg.click("#btnBack"); pg.wait_for_selector("#songs button", timeout=10000)
    check(pg.locator("#viewMap.hide").count() == 1, "지도 화면이 닫힘")
    check(not errs, f"끝까지 JS 에러 없음 {errs[:2]}")
    b.close()

srv.shutdown()
print(f"\n스크린샷: {outdir}")
print(f"결과: {'전부 통과' if not fails else str(len(fails))+'건 실패 → '+str(fails)}")
sys.exit(1 if fails else 0)

# 목록 분리 스모크 — 곡은 위, 문서는 경계선 아래, 문서는 읽기 전용으로 열린다
#   python test_list_ui.py [출력폴더]
import base64, json, sys, threading, http.server, functools, socketserver
from pathlib import Path
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_listtest"
outdir.mkdir(exist_ok=True)

SONGS = ["A01_네온.md", "A07_첫차.md", "B01_주말에.md"]
DOCS  = ["기획_첫차_일탈.md", "작사_스터디_2차_5팀.md", "메타태그_다이내믹_가이드.md"]
DOC_BODY = (
    "# 기획 — 첫차\n\n"
    "한글이 깨지지 않아야 한다 · 토요일 아침\n\n"
    "| 곡 | BPM | 정서 |\n"
    "|---|---|---|\n"
    "| **막차** | 95 | 해학 |\n"
    "| 첫차 | 118 | 즐거움 |\n\n"
    "> 인용도 나와야 한다\n\n"
    "- 목록 항목\n\n"
    "<script>window.__pwned=1</script>\n"
)
SONG_BODY = "**Style of Music:**\n```\ntest style\n```\n\n## 가사\n\n```\n[Verse]\n테스트 가사\n```\n"

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
    if u.rstrip("/").endswith("contents/lyrics"):
        body = json.dumps([{"name": n, "path": "lyrics/" + n, "type": "file"}
                           for n in SONGS + DOCS])
    elif "_plag_index.json" in u:
        idx = json.dumps({"n": 2, "songs": [], "hashes": {}})
        if "vnd.github.raw" in (request.headers.get("accept") or ""):
            return route.fulfill(status=200, headers=CORS,
                                 content_type="application/json", body=idx)
        body = json.dumps({"sha": "s", "content": b64(idx)})
    else:
        # 한글 파일명은 URL 인코딩돼서 오므로 디코드 후 비교한다
        is_doc = any(d in unquote(u) for d in DOCS)
        body = json.dumps({"sha": "s", "content": b64(DOC_BODY if is_doc else SONG_BODY)})
    route.fulfill(status=200, headers=CORS, content_type="application/json", body=body)

fails = []
def check(c, label):
    print(("  [OK] " if c else "  [FAIL] ") + label)
    if not c: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 420, "height": 900})   # 폰 폭
    ctx.add_init_script("localStorage.setItem('yein_tok','test-token')")
    ctx.route("**api.github.com/**", handle)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/index.html")
    pg.wait_for_selector("#songs button", timeout=15000)

    print("\n[1] 곡과 문서가 갈라지는가")
    check(not errs, f"JS 에러 없음 {errs[:2]}")
    n_song, n_doc = pg.locator("#songs button").count(), pg.locator("#docs button").count()
    check(n_song == len(SONGS), f"곡 {n_song}개 (기대 {len(SONGS)})")
    check(n_doc == len(DOCS), f"문서 {n_doc}개 (기대 {len(DOCS)})")
    check(pg.locator("#docsSep:not(.hide)").count() == 1, "경계선 노출")
    songs_txt = pg.locator("#songs").inner_text()
    check(all(d.replace(".md", "").replace("_", " ") not in songs_txt for d in DOCS),
          "문서가 곡 목록에 섞이지 않음")

    print("\n[2] 곡이 문서보다 위에 있는가")
    y_song = pg.locator("#songs button").first.bounding_box()["y"]
    y_sep  = pg.locator("#docsSep").bounding_box()["y"]
    y_doc  = pg.locator("#docs button").first.bounding_box()["y"]
    check(y_song < y_sep < y_doc, f"곡({y_song:.0f}) < 경계선({y_sep:.0f}) < 문서({y_doc:.0f})")
    pg.screenshot(path=str(outdir / "1_목록.png"), full_page=True)

    print("\n[3] 문서는 읽기 전용으로 열리는가")
    pg.locator("#docs button").first.click()
    pg.wait_for_selector("#viewDoc:not(.hide)", timeout=10000)
    pg.wait_for_timeout(600)
    body = pg.locator("#docText").inner_text()
    check("토요일 아침" in body, "한글 본문이 안 깨짐")
    check(pg.locator("#docText table").count() == 1, "표가 진짜 <table> 로 렌더됨")
    check(pg.locator("#docText th").count() == 3, f"표 헤더 3칸 (실제 {pg.locator('#docText th').count()})")
    check(pg.locator("#docText td").count() == 6, f"표 본문 6칸 (실제 {pg.locator('#docText td').count()})")
    check("|" not in body, "파이프 문자가 화면에 안 보임")
    check("**" not in body, "굵게 표시가 별표로 안 새어나옴")
    check(pg.locator("#docText h1").count() == 1, "제목이 <h1> 로 렌더됨")
    check(pg.locator("#docText blockquote").count() == 1, "인용이 <blockquote> 로 렌더됨")
    check(pg.locator("#docText li").count() == 1, "목록이 <li> 로 렌더됨")
    check(pg.evaluate("window.__pwned === undefined"), "문서 속 script 태그가 실행되지 않음")
    check(pg.locator("#docMsg.show").count() == 0, "'가사 블록을 찾지 못했어요' 에러 없음")
    check(pg.locator("#viewEdit.hide").count() == 1, "편집 화면이 안 뜸")
    check(pg.locator("#btnCommit:visible").count() == 0, "[확정] 버튼 없음 (저장 불가)")
    check(len(puts) == 0, "깃허브에 아무것도 안 보냄")
    pg.screenshot(path=str(outdir / "2_문서보기.png"), full_page=False)

    print("\n[4] 곡은 그대로 편집 화면으로 가는가")
    pg.click("#btnBack"); pg.wait_for_selector("#songs button", timeout=10000)
    pg.locator("#songs button").first.click()
    pg.wait_for_selector("#taLyrics", timeout=10000)
    pg.wait_for_timeout(800)
    check("테스트 가사" in pg.locator("#taLyrics").input_value(), "곡은 가사가 편집칸에 들어옴")
    check(not errs, f"끝까지 JS 에러 없음 {errs[:2]}")
    b.close()

srv.shutdown()
print(f"\n스크린샷: {outdir}")
print(f"결과: {'전부 통과' if not fails else str(len(fails))+'건 실패 → '+str(fails)}")
sys.exit(1 if fails else 0)

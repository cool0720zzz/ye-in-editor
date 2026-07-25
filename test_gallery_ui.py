# 갤러리 저장 UI 스모크 테스트 — GitHub API를 가로채 실제 manifest/decisions 로 폰 화면을 띄우고
# [확정]·[전체 저장] 흐름이 눈에 보이게 동작하는지 확인한다.
#   python test_gallery_ui.py <decisions.json> <manifest.json> [출력폴더]
import base64, json, sys, threading, http.server, functools, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
dec_p, man_p = Path(sys.argv[1]), Path(sys.argv[2])
outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "_uitest"
outdir.mkdir(exist_ok=True)

decisions = dec_p.read_text(encoding="utf-8")
manifest = man_p.read_text(encoding="utf-8")
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
                             body=json.dumps({"content": {"sha": "sha%d" % len(puts)}}))
    body = manifest if "manifest.json" in request.url else decisions
    # raw 미디어 타입 요청(manifest 경로)은 파일 원문을 그대로 — 실제 API와 동일하게
    if "vnd.github.raw" in (request.headers.get("accept") or ""):
        return route.fulfill(status=200, headers=CORS,
                             content_type="application/json", body=body)
    route.fulfill(status=200, headers=CORS, content_type="application/json",
                  body=json.dumps({"sha": "sha0", "content": b64(body)}))

fails = []
def check(cond, label):
    print(("  [OK] " if cond else "  [FAIL] ") + label)
    if not cond: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    ctx.add_init_script("localStorage.setItem('yein_tok','test-token')")
    ctx.route("**api.github.com/**", handle)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/gallery.html")
    pg.wait_for_selector(".card", timeout=15000)

    print("\n[1] 첫 화면")
    check(not errs, f"JS 에러 없음 {errs[:2]}")
    check(pg.locator(".card").count() == json.loads(manifest)["items"].__len__(), "카드 전부 렌더")
    check(pg.locator("#commitbar").is_visible(), "하단 저장바가 항상 보임")
    check(pg.locator("#btnSaveAll").is_visible() and pg.locator("#btnCommit").is_visible(),
          "[전체 저장] + [작업 시작] 두 버튼 노출")
    check(pg.locator(".hist").count() > 0, "지난 피드백 기록 블록 노출")
    # 커밋된 데이터면 '작업 지시됨', 폰에서 저장만 한 초안이면 '확정 저장됨'
    want = "확정 저장됨" if json.loads(decisions).get("draft") else "작업 지시됨"
    got = pg.locator(".mystate").first.inner_text()
    check(want in got, f"기존 항목 배지: '{want}' 기대 → '{got}'")
    pg.screenshot(path=str(outdir / "1_첫화면.png"), full_page=False)

    card = pg.locator(".card").filter(has_text="A04").first
    card.scroll_into_view_if_needed()
    card.locator(".hist summary").click()
    pg.wait_for_timeout(200)
    pg.screenshot(path=str(outdir / "2_지난피드백.png"))
    check("바닥쪽" in card.locator(".histnote").first.inner_text(), "지난 피드백 원문이 카드에 보임")

    print("\n[2] 메모 입력 → 미확정 경고")
    ta = card.locator("textarea")
    ta.fill("가방은 크로스백 말고 숄더백으로")
    pg.wait_for_timeout(150)
    check("확정 안 됨" in card.locator(".mystate").inner_text(), "배지가 '확정 안 됨'으로 바뀜")
    check("c-pending" in (card.get_attribute("class") or ""), "카드 테두리 주황 경고")
    check("확정 안 한 항목" in pg.locator("#barinfo").inner_text(), "하단바가 미확정 개수 경고")
    pg.screenshot(path=str(outdir / "3_미확정.png"))

    print("\n[3] [이 항목 확정] 클릭")
    card.locator(".btn-confirm").click()
    pg.wait_for_selector("#toast.show", timeout=5000)
    pg.wait_for_timeout(350)   # 페이드인이 끝난 뒤 찍어야 실제로 읽히는지 알 수 있다
    check("확정 저장됨" in pg.locator("#toast").inner_text(), f"큰 알림 표시: {pg.locator('#toast').inner_text()}")
    check(pg.locator("#toast").evaluate("e=>getComputedStyle(e).opacity") == "1", "알림이 완전히 불투명 — 읽힘")
    pg.screenshot(path=str(outdir / "4_확정토스트.png"))
    check("확정 저장됨" in card.locator(".mystate").inner_text(), "배지가 '확정 저장됨'")
    check(card.locator(".btn-confirm").inner_text().strip() == "✔ 확정됨", "버튼이 '확정됨'으로 변함")
    check(len(puts) >= 1, "GitHub 에 저장 요청이 실제로 나감")

    saved = json.loads(base64.b64decode(puts[-1]["content"]).decode())
    a04 = saved["decisions"]["a04-beonhwaga-crowd"]
    check(saved["draft"] is True, "확정은 초안 저장 (작업 지시는 아님)")
    check(a04["confirmed"] is True, "confirmed 플래그 저장됨")
    # 기존 이력 개수는 데이터마다 다르다(구형식=승격 1건, 신형식=쌓인 만큼) — 상대 검증
    base_h = json.loads(decisions)["decisions"]["a04-beonhwaga-crowd"].get("history", [])
    base_n = len([h for h in base_h if h.get("choice") or (h.get("notes") or "").strip()]) or 1
    check(len(a04["history"]) == base_n + 1,
          f"피드백이 기존 {base_n}건 + 새 1건으로 누적됨 (실제 {len(a04['history'])}건)")
    prev = [(h.get("notes") or "") for h in base_h
            if h.get("choice") or (h.get("notes") or "").strip()]
    kept = [(h.get("notes") or "") for h in a04["history"][:-1]]
    preserved = (kept == prev) if prev else (len(kept) == 1)   # 구형식이면 승격분 1건
    check("숄더백" in a04["history"][-1]["notes"] and preserved, "옛 피드백 + 새 피드백 둘 다 보존")

    print("\n[4] [작업 시작] 클릭")
    pg.locator("#btnCommit").click()
    pg.wait_for_timeout(1200)
    check("작업 시작" in pg.locator("#toast").inner_text(), "커밋 알림 표시")
    committed = json.loads(base64.b64decode(puts[-1]["content"]).decode())
    check(committed["draft"] is False, "draft=false 로 커밋됨")
    check(all(c.get("committed") for c in committed["decisions"].values() if c.get("choice")),
          "선택된 항목 전부 committed 처리")
    check("모두 저장됨" in pg.locator("#barinfo").inner_text(), "하단바가 '모두 저장됨'")
    pg.screenshot(path=str(outdir / "5_작업시작.png"))
    check(not errs, f"끝까지 JS 에러 없음 {errs[:2]}")
    b.close()

srv.shutdown()
print(f"\n스크린샷: {outdir}")
print(f"결과: {'전부 통과' if not fails else str(len(fails)) + '건 실패 → ' + str(fails)}")
sys.exit(1 if fails else 0)

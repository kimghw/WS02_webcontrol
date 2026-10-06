"""web_probe — 범용 웹 정탐(읽기 전용): 채널·탭 상태, 화면 인벤토리(+캡처·요청/응답·초안), 사용자 실연 캡처(watch),
inventory → fieldmap 초안, 조작 전/후 인벤토리 비교. 사이트 지식 없이 어느 CDP 채널에나 붙는다.

⚠ 읽기 전용 — 이 스크립트는 저장·제출·삭제는 물론 어떤 클릭·입력도 하지 않는다. 허용된 조작은 새 탭 열기/닫기·
URL 이동뿐이다. 로그인·OTP·기기인증은 사용자가 브라우저에서 직접 한다(--wait-ready 로 그동안 대기).
watch 는 관찰만 한다 — 사용자가 직접 조작하는 동안 이벤트·네트워크를 기록한다(사용자 감독 하 실연 캡처).

usage (stdout JSON 1개, help 만 텍스트):
  python probes/web_probe.py status   --port N
  python probes/web_probe.py snapshot --port N [--tab 부분문자열 | --url U] [--wait-ready SEL] [--net [--net-seconds S]]
                                      [--bodies] [--keep] [--out DIR] [--name KEY]
  python probes/web_probe.py watch    --port N [--tab 부분문자열 | --url U] [--seconds 180] [--values] [--bodies]
                                      [--no-inventory] [--out DIR] [--name KEY]
  python probes/web_probe.py draft    --inventory <inventory.json> [--anchor SEL] [--out FILE]
  python probes/web_probe.py diff     --before <inventory.json> --after <inventory.json> [--out FILE]
공통: --port(기본 CDP_PORT 환경변수 — 없으면 오류: 채널은 SSO 경계마다 다르므로 추측하지 않는다) · --env FILE
출력: probes/out/<action>_<key>_<ts>/{inventory.json, shot.png, fieldmap.draft.yaml, net.json, events.jsonl,
      actions.json, inventory_before/after.json, diff.json, steps.jsonl}
exit: 0 ok · 1 오류 · 2 채널/대상 없음 · 3 wait_user(준비 셀렉터 미등장) · 6 수집 0건
엔진은 web_core/(cdp_channel·page_inventory·probe_kit) — 이 파일은 조립·CLI·출력만.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from web_core import cdp_channel as ch  # noqa: E402
from web_core import page_inventory as inv  # noqa: E402
from web_core import probe_kit as kit  # noqa: E402

EXIT_OK, EXIT_ERR, EXIT_MISSING, EXIT_WAIT_USER, EXIT_EMPTY = 0, 1, 2, 3, 6
OUT_BASE = ROOT / "probes" / "out"

HELP = """web_probe — 범용 웹 정탐(읽기 전용, 사이트 무관)

action     설명
status     채널 생존(/json/version) + 열린 탭 목록. playwright 불필요, 부작용 없음
snapshot   대상 탭(--tab 부분문자열, 기본: 마지막 활성 일반 탭) 또는 --url 새 탭의 프레임/컨트롤 인벤토리 + 전체 캡처
           + fieldmap 초안. --net 이면 요청/응답 요약(--url: 첫 요청부터, 기존 탭: --net-seconds 동안)
watch      사용자 실연 캡처 — 사용자가 직접 조작하는 동안(--seconds, 또는 출력 폴더에 STOP 파일 생성 시 종료)
           클릭·변경·제출·Enter/Tab, 팝업/네비게이션/다이얼로그, 요청/응답(POST 키·postback 대상)을 기록.
           시작/끝 인벤토리와 diff 도 남긴다. 스크립트는 아무것도 클릭·입력하지 않는다
draft      inventory.json → fieldmap.draft.yaml (오프라인)
diff       조작 전/후 inventory.json 비교 → 늘어난/사라진 컨트롤 (오프라인)
help       이 표

옵션: --port N · --env FILE · --tab S · --url U · --out DIR|FILE · --name KEY(출력 폴더 이름) · --keep(연 탭 유지) ·
      --wait-ready SEL(이 셀렉터가 보일 때까지 --wait-user 초 대기 — 로그인 등 사용자 조치용) · --net · --bodies(응답 본문) ·
      --values(입력값·POST 원문 기록 — 개인정보 주의, 기본 마스킹) · --seconds N(watch) · --no-inventory(watch)
exit: 0 ok · 1 오류 · 2 채널/대상 없음 · 3 wait_user · 6 수집 0건
"""


def missing_port() -> int:
    return kit.emit({"ok": False, "error": "포트 미지정",
                     "hint": "--port N 또는 CDP_PORT 를 지정 — 대상 사이트의 채널은 spec/spec_아키텍처.md ② 채널 표에서 고른다"},
                    EXIT_ERR)


def stopped(action: str, port: int) -> int:
    return kit.emit({"ok": False, "action": action, "port": port, "state": "stopped",
                     "hint": f"채널 {port} 이 응답하지 않음 — set_cdp_chrome launch {port} 또는 바탕화면 아이콘으로 기동"},
                    EXIT_MISSING)


def tab_list(port: int) -> list[dict]:
    return [{"index": i, "url": t["url"][:200], "title": t["title"][:60]} for i, t in enumerate(ch.page_targets(port))]


def _ordinary(url: str) -> bool:
    u = (url or "").lower()
    return not u.startswith(("devtools://", "chrome://", "chrome-extension://", "about:blank", "edge://"))


def pick_tab(ctx, needle: str | None):
    """--tab 부분문자열(URL/제목) 일치 탭 중 마지막, 없으면 마지막 일반 탭."""
    pages = [pg for pg in ctx.pages if _ordinary(ch.page_url(pg))]
    if needle:
        n = needle.lower()
        pages = [pg for pg in pages if n in ch.page_url(pg).lower() or n in ch.page_title(pg).lower()]
    return pages[-1] if pages else None


def open_or_pick(ctx, a, run: kit.Run, before_goto=None, dismiss_dialogs: bool = True):
    """(page, opened) — --url 이면 새 탭, 아니면 기존 탭 선택. 대상 없으면 (None, False).
    before_goto(page): 새 탭에서 goto 전에 부를 콜백(네트워크 캡처·기록기를 첫 요청부터 붙일 때).
    dismiss_dialogs: snapshot 은 새 탭의 다이얼로그를 닫고, watch 는 사용자가 직접 응답하도록 건드리지 않는다."""
    if a.url:
        page = ctx.new_page()
        if dismiss_dialogs:
            page.on("dialog", lambda d: d.dismiss())
        if before_goto is not None:
            before_goto(page)
        page.goto(a.url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        run.step("open", url=a.url[:160])
        return page, True
    page = pick_tab(ctx, a.tab)
    if page is not None:
        run.step("pick", url=ch.page_url(page)[:160], title=ch.page_title(page)[:60])
    return page, False


def wait_ready(page, a, run: kit.Run) -> bool:
    if not a.wait_ready:
        return True
    polls = max(1, int(a.wait_user * 1000 / 400))
    fr = inv.wait_selector(page, a.wait_ready, polls=polls)
    run.step("wait_ready", selector=a.wait_ready, found=fr is not None)
    return fr is not None


def inventory_page(page, run: kit.Run, name: str = "inventory.json", screenshot: bool = True,
                   draft: bool = True, anchor: str | None = None) -> dict:
    """프레임 인벤토리 + 캡처 + (편집 컨트롤이 있으면) 초안. 파일 경로와 요약."""
    frames = inv.scan_frames(page)
    total = inv.total_fields(frames)
    inventory = {"ts": run.ts, "url": ch.page_url(page), "title": ch.page_title(page), "frames": frames}
    files = {name.replace(".json", ""): run.write_json(name, inventory)}
    run.step("inventory.scan", file=name, frames=len(frames), fields=total)
    if screenshot:
        try:
            p = run.ensure() / name.replace("inventory", "shot").replace(".json", ".png")
            page.screenshot(path=str(p), full_page=True)
            files["screenshot" if p.name == "shot.png" else p.stem] = str(p)
        except Exception as e:  # noqa: BLE001
            run.step("inventory.screenshot", error=str(e)[:120])
    summary = None
    if draft:
        form_fr = inv.pick_form_frame(frames)
        if form_fr and any(inv.editable(f) for f in form_fr.get("fields") or []):
            text = inv.fieldmap_draft(inventory, source=files[name.replace(".json", "")], anchor=anchor)
            files["draft"] = run.write_text("fieldmap.draft.yaml", text)
            summary = inv.draft_summary(text)
    return {"files": files, "frames": len(frames), "fields": total, "url": ch.page_url(page)[:200],
            "title": ch.page_title(page)[:80], "draft_summary": summary, "inventory": inventory,
            "frame_urls": [(f.get("name") or "") + " | " + (f.get("url") or "")[:100] for f in frames]}


# ── actions ───────────────────────────────────────────────────────────
def act_status(a) -> int:
    if a.port is None:
        return missing_port()
    chn = ch.channel_info(a.port)
    if chn is None:
        return stopped("status", a.port)
    tabs = tab_list(a.port)
    return kit.emit({"ok": True, "action": "status", "port": a.port, "state": "listening", **chn, "tabs": tabs,
                     "hint": "snapshot --tab <부분문자열> 로 화면 인벤토리, watch 로 사용자 실연 캡처"}, EXIT_OK)


def act_snapshot(a) -> int:
    if a.port is None:
        return missing_port()
    if ch.channel_info(a.port) is None:
        return stopped("snapshot", a.port)
    run = kit.Run("snapshot", a.name or a.tab or ("url" if a.url else "current"), a.out, OUT_BASE)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _, ctx = ch.connect(p, a.port)
        run.step("attach", port=a.port, pages=len(ctx.pages))
        net = kit.NetCapture(values=a.values, bodies=a.bodies) if a.net else None
        page, opened = open_or_pick(ctx, a, run, before_goto=net.attach if net else None)
        if page is None:
            return kit.emit({"ok": False, "action": "snapshot", "port": a.port, "state": "no_tab", "tabs": tab_list(a.port),
                             "hint": "대상 탭 없음 — --tab 부분문자열 또는 --url 지정"}, EXIT_MISSING)
        if net is not None and not opened:
            net.attach(page)
        if not wait_ready(page, a, run):
            return kit.emit({"ok": False, "action": "snapshot", "port": a.port, "state": "wait_user",
                             "url": ch.page_url(page)[:200], "wait_ready": a.wait_ready,
                             "hint": "준비 셀렉터가 나타나지 않음 — 사용자가 로그인/화면 이동을 마친 뒤 재실행(탭 유지)",
                             "out": str(run.dir)}, EXIT_WAIT_USER)
        if net is not None and not opened:
            page.wait_for_timeout(int(a.net_seconds * 1000))
        s = inventory_page(page, run, anchor=a.anchor)
        if net is not None:
            s["files"]["net"] = run.write_json("net.json", net.items)
        closed = kit.close_if(page, opened, a.keep)
        s.pop("inventory")
        result = {"ok": s["fields"] > 0, "action": "snapshot", "port": a.port, **s, "net": len(net.items) if net else None,
                  "opened_tab": opened, "closed_tab": closed, "out": str(run.dir)}
        if s["fields"] == 0:
            result.update(error="PROBE_EMPTY", hint="수집 컨트롤 0건 — 대상 탭/프레임·로딩 확인(shot.png)")
            return kit.emit(result, EXIT_EMPTY)
        result["hint"] = ("fieldmap.draft.yaml 검토 후 recipe 승격" if s["draft_summary"]
                          else "편집 가능 컨트롤 없음 — 목록/조회 화면이면 inventory.json·net.json 만 참고")
        return kit.emit(result, EXIT_OK)


def act_watch(a) -> int:
    if a.port is None:
        return missing_port()
    if ch.channel_info(a.port) is None:
        return stopped("watch", a.port)
    run = kit.Run("watch", a.name or a.tab or ("url" if a.url else "current"), a.out, OUT_BASE)
    stop_file = run.ensure() / "STOP"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _, ctx = ch.connect(p, a.port)
        run.step("attach", port=a.port, pages=len(ctx.pages))
        net = kit.NetCapture(values=a.values, bodies=a.bodies)
        rec = kit.Recorder(ctx, values=a.values, net=net, sink=run.ensure() / "events.jsonl")
        page, opened = open_or_pick(ctx, a, run, before_goto=rec.watch, dismiss_dialogs=False)
        if page is None:
            return kit.emit({"ok": False, "action": "watch", "port": a.port, "state": "no_tab", "tabs": tab_list(a.port),
                             "hint": "대상 탭 없음 — --tab 부분문자열 또는 --url 지정"}, EXIT_MISSING)
        files: dict = {}
        before = None
        if not a.no_inventory:
            b = inventory_page(page, run, name="inventory_before.json", draft=False)
            before = b["inventory"]
            files.update(b["files"])
        rec.watch(page)            # --url 이면 goto 전에 이미 붙었다(중복 무시)
        rec.follow_new_pages()
        run.step("watch.start", seconds=a.seconds, url=ch.page_url(page)[:160], stop_file=str(stop_file))
        # 사용자에게 시작을 알리는 신호는 stderr 1줄(stdout JSON 1개 계약 유지)
        print(f"[watch] 기록 시작 — {a.seconds}s 또는 STOP 파일({stop_file}) 생성 시 종료", file=sys.stderr, flush=True)
        deadline = time.time() + max(1, a.seconds)
        reason = "timeout"
        tick = 0
        while time.time() < deadline:
            if stop_file.exists():
                reason = "stop_file"
                break
            if page.is_closed():
                reason = "page_closed"
                break
            page.wait_for_timeout(500)
            tick += 1
            if tick % 6 == 0:
                rec.reinstall()
        run.step("watch.stop", reason=reason, events=len(rec.events), net=len(net.items))
        actions = rec.actions()
        files["events"] = str(run.dir / "events.jsonl")
        files["actions"] = run.write_json("actions.json", actions)
        files["net"] = run.write_json("net.json", net.items)
        diff = None
        if not a.no_inventory and not page.is_closed():
            aft = inventory_page(page, run, name="inventory_after.json", draft=True, anchor=a.anchor)
            files.update(aft["files"])
            diff = inv.inventory_diff(before or {}, aft["inventory"])
            files["diff"] = run.write_json("diff.json", diff)
        closed = kit.close_if(page, opened, a.keep)
        kinds: dict[str, int] = {}
        for e in rec.events:
            kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
        posts = [{"method": i["method"], "url": i["url"][:160], "status": i["status"],
                  "event_target": (i.get("post") or {}).get("__EVENTTARGET")} for i in net.posts()][:40]
        user_ops = sum(kinds.get(k, 0) for k in ("click", "change", "submit", "key"))
        result = {"ok": user_ops > 0, "action": "watch", "port": a.port, "stop_reason": reason,
                  "pages": len(rec.pages), "events": kinds, "actions": len(actions), "net": len(net.items),
                  "posts": posts, "diff": {"added": len(diff["added"]), "removed": len(diff["removed"])} if diff else None,
                  "values_recorded": a.values, "files": files, "opened_tab": opened, "closed_tab": closed,
                  "out": str(run.dir)}
        if user_ops == 0:
            result.update(error="NO_USER_ACTION", hint="기록된 사용자 조작 0건 — 대상 탭이 맞는지, 조작이 기록 시간 안이었는지 확인")
            return kit.emit(result, EXIT_EMPTY)
        result["hint"] = "actions.json(조작 순서)·net.json(저장/조회 요청)·diff.json 을 recipe(context·fieldmap)와 runner 설계에 귀속"
        return kit.emit(result, EXIT_OK)


def act_draft(a) -> int:
    if not a.inventory:
        return kit.emit({"ok": False, "action": "draft", "error": "--inventory 경로 필요"}, EXIT_ERR)
    src = Path(a.inventory)
    if not src.exists():
        return kit.emit({"ok": False, "action": "draft", "error": f"파일 없음: {src}"}, EXIT_MISSING)
    inventory = json.loads(src.read_text(encoding="utf-8"))
    text = inv.fieldmap_draft(inventory, form_id=a.form_id, source=str(src), anchor=a.anchor)
    out = Path(a.out) if a.out else src.with_name("fieldmap.draft.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return kit.emit({"ok": True, "action": "draft", "inventory": str(src), "out": str(out),
                     "draft_summary": inv.draft_summary(text), "lines": text.count("\n"),
                     "hint": "초안 — 검증 전 러너 사용 금지"}, EXIT_OK)


def act_diff(a) -> int:
    if not (a.before and a.after):
        return kit.emit({"ok": False, "action": "diff", "error": "--before 와 --after 필요"}, EXIT_ERR)
    try:
        b = json.loads(Path(a.before).read_text(encoding="utf-8"))
        af = json.loads(Path(a.after).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        return kit.emit({"ok": False, "action": "diff", "error": f"파일 없음: {e.filename}"}, EXIT_MISSING)
    d = inv.inventory_diff(b, af)
    out = None
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        out = a.out
    return kit.emit({"ok": True, "action": "diff", "added": d["added"][:80], "removed": d["removed"][:80],
                     "n_added": len(d["added"]), "n_removed": len(d["removed"]), "out": out}, EXIT_OK)


# ── CLI ───────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="범용 웹 정탐(읽기 전용)", add_help=False)
    ap.add_argument("action", nargs="?", default="help",
                    choices=["status", "snapshot", "watch", "draft", "diff", "help", "-h", "--help"])
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--env", default=None, help="KEY=VALUE 파일(CDP_PORT 등). 값은 출력하지 않는다")
    ap.add_argument("--tab", default=None, help="대상 탭(URL/제목 부분문자열)")
    ap.add_argument("--url", default=None, help="새 탭으로 열 URL")
    ap.add_argument("--out", default=None)
    ap.add_argument("--name", default=None, help="출력 폴더 키(기본: tab/url/current)")
    ap.add_argument("--keep", action="store_true", help="이 실행이 연 탭을 닫지 않는다")
    ap.add_argument("--wait-ready", default=None, help="이 셀렉터가 어느 frame 에든 나타날 때까지 대기")
    ap.add_argument("--wait-user", type=int, default=60, help="--wait-ready 대기(초)")
    ap.add_argument("--net", action="store_true", help="요청/응답 요약 캡처(snapshot)")
    ap.add_argument("--net-seconds", type=float, default=5.0, help="기존 탭 snapshot 의 --net 캡처 시간")
    ap.add_argument("--bodies", action="store_true", help="xhr/fetch 응답 본문(20KB 이하) 저장")
    ap.add_argument("--values", action="store_true", help="입력값·POST 원문 기록(기본 마스킹 — 개인정보 주의)")
    ap.add_argument("--seconds", type=int, default=180, help="watch 기록 시간(초)")
    ap.add_argument("--no-inventory", action="store_true", help="watch 시작/끝 인벤토리 생략")
    ap.add_argument("--anchor", default=None, help="초안 frame_reacquire 앵커 셀렉터")
    ap.add_argument("--form-id", default=None, help="초안 form_id 표기")
    ap.add_argument("--inventory", default=None, help="draft 입력 inventory.json")
    ap.add_argument("--before", default=None)
    ap.add_argument("--after", default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.action in ("help", "-h", "--help"):
        print(HELP)
        return EXIT_OK
    loaded = kit.load_env(Path(a.env)) if a.env else []
    a.port = ch.resolve_port(a.port)
    try:
        return {"status": act_status, "snapshot": act_snapshot, "watch": act_watch,
                "draft": act_draft, "diff": act_diff}[a.action](a)
    except Exception as e:  # noqa: BLE001
        return kit.emit({"ok": False, "action": a.action, "port": a.port, "error": f"{type(e).__name__}: {str(e)[:300]}",
                         "env_keys": loaded, "hint": "채널 생존(status)·playwright 설치·URL 을 확인"}, EXIT_ERR)


if __name__ == "__main__":
    sys.exit(main())

"""ea_eclass_probe — KRS eclass 전자결재(e-Approval) 정탐(읽기 전용): 채널·세션 상태, 결재양식함 카탈로그,
폼 프레임/컨트롤 인벤토리(+요청/응답), fieldmap DSL v1 초안.

⚠ 읽기 전용 — 저장·상신·삭제·행추가 클릭 없음. 허용된 조작은 (1) 새 탭 열기/닫기·URL 이동
(2) RealEANet 성명 핸드셰이크(--ea-name 또는 KRS_EA_NAME) 뿐. gate 로그인·OTP·기기인증은 자동 통과하지 않고
wait_user 로 보고한다(탭은 열어 둔다 — 사용자가 처리한 뒤 재실행).

확인 대상 1) CDP 채널 생존·열린 eclass 탭 2) 세션 단계 3) 결재양식함 FORMID 카탈로그
4) 폼 프레임 구조·컨트롤·포스트백 앵커·(옵션) XHR 요청/응답 5) DSL v1 fieldmap 초안.

usage (stdout JSON 1개, help 만 텍스트):
  python probes/ea_eclass_probe.py status   [--port 9333]
  python probes/ea_eclass_probe.py forms    [--port] [--keep] [--out DIR]
  python probes/ea_eclass_probe.py form     --form-id KR_EA_Form2_Test [--url U] [--net] [--wait-user 45]
                                            [--ea-name 성명] [--keep] [--out DIR]
  python probes/ea_eclass_probe.py snapshot [--tab 부분문자열 | --url U] [--net] [--keep] [--out DIR]
  python probes/ea_eclass_probe.py draft    --inventory probes/out/<run>/inventory.json [--form-id ID] [--out FILE]
공통: --port(기본 ECLASS_CDP_PORT > 9333) · --env .env.eclass(KEY=VALUE, 비밀 출력 안 함)
출력: probes/out/<action>_<key>_<ts>/{inventory.json, shot.png, fieldmap.draft.yaml, forms.json, net.json, steps.jsonl}
exit: 0 ok · 1 오류 · 2 채널/대상 없음 · 3 wait_user(사용자 조치) · 4 진입 거부(MsgBox) · 6 수집 0건
엔진은 공용 web_core/(cdp_channel·page_inventory·probe_kit) + eclass 전용 ea_approval/ea_core/(eclass_session·
eclass_inventory) — 이 파일은 조립·CLI·출력만. 범용 정탐(사이트 무관·사용자 실연 watch)은 probes/web_probe.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
EA_DIR = ROOT / "ea_approval"
for _p in (ROOT, EA_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from ea_core import eclass_inventory as inv  # noqa: E402
from ea_core import eclass_session as es  # noqa: E402
from web_core import cdp_channel as ch  # noqa: E402
from web_core import probe_kit as kit  # noqa: E402
from web_core.probe_kit import NetCapture, close_if, emit, load_env  # noqa: E402,F401

EXIT_OK, EXIT_ERR, EXIT_MISSING, EXIT_WAIT_USER, EXIT_REJECTED, EXIT_EMPTY = 0, 1, 2, 3, 4, 6
OUT_BASE = ROOT / "probes" / "out"

HELP = """ea_eclass_probe — eclass 전자결재 정탐(읽기 전용)

action     설명
status     채널 생존(/json/version) + 열린 탭 분류 + 세션 힌트. playwright 불필요, 부작용 없음
forms      결재양식함(양식선택) 카탈로그 → {label, form_id, url}. e-Approval 탭이 없으면 새 탭으로 열고 닫는다
form       --form-id 폼을 loginbyname?ReturnUrl 경유로 새 탭에 열어 프레임/컨트롤 인벤토리 + 캡처 + 초안
snapshot   지금 보고 있는 탭(또는 --tab/--url)의 인벤토리 + 캡처 + 초안 — 사용자가 직접 연 화면 캡처용
draft      inventory.json → fieldmap.draft.yaml (오프라인)
help       이 표

옵션: --port N · --env FILE · --out DIR|FILE · --keep(연 탭 유지) · --net(요청/응답 캡처) ·
      --wait-user SEC(로그인·성명 대기, form/forms/snapshot) · --ea-name 성명(성명 핸드셰이크 자동)
exit: 0 ok · 1 오류 · 2 채널/대상 없음 · 3 wait_user · 4 진입 거부 · 6 수집 0건
"""


# ── 공통 유틸(실행 골격·네트워크 캡처·env 는 web_core.probe_kit) ─────────────
def Run(action: str, key: str, out: str | None) -> kit.Run:  # noqa: N802 — 기존 호출부 호환
    return kit.Run(action, key, out, OUT_BASE)


def channel_or_exit(port: int) -> dict | None:
    return ch.channel_info(port)


def wait_session(page, run: kit.Run, wait_user: int, ea_name: str | None) -> dict:
    """세션 단계가 ok 가 될 때까지 (성명 핸드셰이크 1회 시도 →) 사용자 조치 대기. {state, url, text, handshake}."""
    tried = False
    deadline = time.time() + max(0, wait_user)
    last = es.page_state(page)
    while True:
        st = last["state"]
        if st == es.NEEDS_NAME and ea_name and not tried:
            tried = True
            ok = es.pass_name_handshake(page, ea_name)
            run.step("session.handshake", ok=ok)
            page.wait_for_timeout(1500)
            last = es.page_state(page)
            continue
        if st in es.WAIT_USER_STATES and time.time() < deadline:
            page.wait_for_timeout(1000)
            last = es.page_state(page)
            continue
        last["handshake"] = tried
        return last


def inventory_page(page, run: kit.Run, form_id: str | None, net: NetCapture | None, screenshot: bool = True) -> dict:
    """프레임 인벤토리 + 캡처 + (폼이면) 초안. 파일 경로와 요약을 돌려준다."""
    frames = inv.scan_frames(page)
    total = inv.total_fields(frames)
    state = es.page_state(page)
    fid = form_id or es.form_id_from_url(state.get("url") or "")
    inventory = {"form_id": fid, "ts": run.ts, "url": state.get("url"), "state": state.get("state"),
                 "title": None, "frames": frames}
    try:
        inventory["title"] = page.title()
    except Exception:
        pass
    files = {"inventory": run.write_json("inventory.json", inventory)}
    run.step("inventory.scan", frames=len(frames), fields=total)
    if screenshot:
        try:
            p = run.ensure() / "shot.png"
            page.screenshot(path=str(p), full_page=True)
            files["screenshot"] = str(p)
        except Exception as e:  # noqa: BLE001
            run.step("inventory.screenshot", error=str(e)[:120])
    cat = inv.catalog_frame(page)
    catalog_n = None
    if cat is not None:
        try:
            raw = cat.evaluate(inv.CATALOG_JS)
            forms = inv.assign_categories(inv.dedupe_forms(raw.get("forms") or []), raw.get("tabs") or [])
            files["forms"] = run.write_json("forms.json", {"ts": run.ts, "tabs": raw.get("tabs"), "forms": forms})
            catalog_n = len(forms)
        except Exception as e:  # noqa: BLE001
            run.step("inventory.catalog", error=str(e)[:120])
    form_fr = inv.pick_form_frame(frames)
    draft_written = False
    if form_fr and any(inv.editable(f) for f in form_fr.get("fields") or []):
        files["draft"] = run.write_text("fieldmap.draft.yaml",
                                        inv.fieldmap_draft(inventory, fid, files["inventory"]))
        draft_written = True
    if net is not None:
        files["net"] = run.write_json("net.json", net.items)
    ready = {"toolbar": inv.toolbar_frame(page) is not None, "form": inv.form_frame(page) is not None,
             "editor": inv.frame_with(page, es.SEL["editor_body"]) is not None}
    return {"files": files, "frames": len(frames), "fields": total, "state": state.get("state"),
            "url": (state.get("url") or "")[:200], "form_id": fid, "ready": ready, "draft": draft_written,
            "catalog_forms": catalog_n,
            "frame_urls": [(f.get("name") or "") + " | " + (f.get("url") or "")[:100] for f in frames]}


# ── actions ───────────────────────────────────────────────────────────
def act_status(a) -> int:
    port = a.port
    chn = channel_or_exit(port)
    if chn is None:
        return emit({"ok": False, "action": "status", "port": port, "state": "stopped",
                     "hint": f"채널 {port} 이 응답하지 않음 — set_cdp_chrome launch {port} 또는 바탕화면 아이콘으로 기동"},
                    EXIT_MISSING)
    tabs = es.tab_summary(ch.page_targets(port))
    return emit({"ok": True, "action": "status", "port": port, "state": "listening", **chn,
                 "session_hint": es.session_hint(tabs), "tabs": tabs,
                 "hint": {"needs_login": "eclass 로그인 탭이 열려 있음 — 사용자가 로그인한 뒤 재실행",
                          "eapproval_open": "e-Approval 탭 있음 — forms / form --form-id 진행 가능",
                          "eclass_open": "eclass 탭은 있으나 e-Approval 은 아님 — forms 가 새 탭으로 연다",
                          "no_eclass_tab": "eclass 탭 없음 — forms 가 새 탭으로 열되 로그인은 사용자 몫"}[es.session_hint(tabs)]},
                EXIT_OK)


def act_forms(a) -> int:
    port = a.port
    if channel_or_exit(port) is None:
        return emit({"ok": False, "action": "forms", "port": port, "state": "stopped",
                     "hint": "채널이 응답하지 않음 — status 로 확인"}, EXIT_MISSING)
    run = Run("forms", "catalog", a.out)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _, ctx = ch.connect(p, port)
        run.step("attach", port=port, pages=len(ctx.pages))
        pages = [pg for pg in ctx.pages if es.tab_kind(ch.page_url(pg)) == "eapproval"]
        page, opened = (pages[-1], False) if pages else (None, False)
        fr = inv.catalog_frame(page) if page is not None else None
        if fr is None:
            page = ctx.new_page()
            opened = True
            page.on("dialog", lambda d: d.dismiss())
            page.goto(es.EAPPROVAL_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            run.step("open", url=es.EAPPROVAL_URL[:120])
            st = wait_session(page, run, a.wait_user, a.ea_name)
            if st["state"] in es.WAIT_USER_STATES:
                run.step("session", state=st["state"])
                return emit({"ok": False, "action": "forms", "port": port, "state": st["state"], "url": st["url"][:200],
                             "hint": "사용자가 브라우저에서 로그인/성명 입력을 마친 뒤 재실행(탭은 열어 둠)",
                             "out": str(run.dir)}, EXIT_WAIT_USER)
            if st["state"] == es.REJECTED:
                close_if(page, opened, a.keep)
                return emit({"ok": False, "action": "forms", "port": port, "state": "rejected",
                             "message": st.get("text"), "out": str(run.dir)}, EXIT_REJECTED)
            fr = inv.wait_for(page, lambda: inv.catalog_frame(page), polls=30)
        if fr is None:
            close_if(page, opened, a.keep)
            return emit({"ok": False, "action": "forms", "port": port, "state": "no_catalog_frame",
                         "frames": [inv.frame_url(f)[:120] for f in page.frames],
                         "hint": "결재양식함(SelectBaseFormTypeB) 프레임을 찾지 못함 — e-Approval 좌측 메뉴 '결재양식함' 을 연 뒤 재실행",
                         "out": str(run.dir)}, EXIT_MISSING)
        raw = fr.evaluate(inv.CATALOG_JS)
        forms = inv.assign_categories(inv.dedupe_forms(raw.get("forms") or []), raw.get("tabs") or [])
        path = run.write_json("forms.json", {"ts": run.ts, "url": raw.get("url"), "tabs": raw.get("tabs"), "forms": forms})
        run.step("catalog", forms=len(forms), tabs=len(raw.get("tabs") or []))
        closed = close_if(page, opened, a.keep)
        return emit({"ok": len(forms) > 0, "action": "forms", "port": port, "count": len(forms),
                     "tabs": raw.get("tabs"), "forms": forms, "opened_tab": opened, "closed_tab": closed,
                     "files": {"forms": path}, "out": str(run.dir),
                     "hint": "form --form-id <FORMID> 로 폼 인벤토리 진행" if forms else "카탈로그 0건 — 프레임/권한 확인"},
                    EXIT_OK if forms else EXIT_EMPTY)


def act_form(a) -> int:
    port = a.port
    form_id = a.form_id or (es.form_id_from_url(a.url) if a.url else None)
    if not form_id and not a.url:
        return emit({"ok": False, "action": "form", "error": "--form-id 또는 --url 필요"}, EXIT_ERR)
    url = a.url or es.build_entry_url(form_id)
    if channel_or_exit(port) is None:
        return emit({"ok": False, "action": "form", "port": port, "state": "stopped",
                     "hint": "채널이 응답하지 않음 — status 로 확인"}, EXIT_MISSING)
    run = Run("form", form_id or "url", a.out)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _, ctx = ch.connect(p, port)
        run.step("attach", port=port, pages=len(ctx.pages))
        page = ctx.new_page()
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.message[:120]), d.dismiss()))
        net = NetCapture(page) if a.net else None
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        run.step("open", url=url[:160])
        st = wait_session(page, run, a.wait_user, a.ea_name)
        run.step("session", state=st["state"], url=(st.get("url") or "")[:160], handshake=st.get("handshake"))
        if st["state"] in es.WAIT_USER_STATES:
            return emit({"ok": False, "action": "form", "port": port, "form_id": form_id, "state": st["state"],
                         "url": (st.get("url") or "")[:200], "handshake_tried": st.get("handshake"),
                         "hint": {"needs_login": "gate/eclass 로그인 필요 — 열린 탭에서 사용자가 로그인 후 재실행",
                                  "needs_name": "RealEANet 성명 핸드셰이크 필요 — 탭에서 성명 입력 후 재실행(또는 --ea-name)",
                                  "needs_otp": "OTP 입력은 사용자 직접 — 통과 후 재실행",
                                  "needs_device_auth": "기기(PC) 인증은 사용자 직접 — 통과 후 재실행"}[st["state"]],
                         "out": str(run.dir)}, EXIT_WAIT_USER)
        if st["state"] == es.REJECTED:
            close_if(page, True, a.keep)
            return emit({"ok": False, "action": "form", "port": port, "form_id": form_id, "state": "rejected",
                         "url": (st.get("url") or "")[:200], "message": st.get("text"),
                         "hint": "DocumentView 진입 거부(MsgBox) — loginbyname 경유 여부·FORMID·권한 확인",
                         "out": str(run.dir)}, EXIT_REJECTED)
        if st["state"] == es.NOT_ECLASS:
            close_if(page, True, a.keep)
            return emit({"ok": False, "action": "form", "port": port, "form_id": form_id, "state": "not_eclass",
                         "url": (st.get("url") or "")[:200], "hint": "eclass origin 이 아님 — URL 확인",
                         "out": str(run.dir)}, EXIT_REJECTED)
        ready = inv.wait_form_ready(page, polls=a.polls)
        run.step("form.ready", **ready)
        page.wait_for_timeout(1500)
        summary = inventory_page(page, run, form_id, net)
        closed = close_if(page, True, a.keep)
        result = {"ok": summary["fields"] > 0, "action": "form", "port": port, "form_id": form_id,
                  "state": summary["state"], "url": summary["url"], "ready": ready, "dialogs": dialogs,
                  "frames": summary["frames"], "fields": summary["fields"], "draft": summary["draft"],
                  "frame_urls": summary["frame_urls"], "files": summary["files"], "closed_tab": closed,
                  "out": str(run.dir)}
        if summary["fields"] == 0:
            result["error"] = "PROBE_EMPTY"
            result["hint"] = "수집 필드 0건 — 폼 미로딩/차단 의심(shot.png 확인)"
            return emit(result, EXIT_EMPTY)
        result["hint"] = "fieldmap.draft.yaml 을 검토해 recipe(fieldmap·input.template·context) 로 승격"
        return emit(result, EXIT_OK)


def act_snapshot(a) -> int:
    port = a.port
    if channel_or_exit(port) is None:
        return emit({"ok": False, "action": "snapshot", "port": port, "state": "stopped",
                     "hint": "채널이 응답하지 않음 — status 로 확인"}, EXIT_MISSING)
    key = a.tab or ("url" if a.url else "current")
    run = Run("snapshot", key, a.out)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        _, ctx = ch.connect(p, port)
        run.step("attach", port=port, pages=len(ctx.pages))
        page, opened = None, False
        net = None
        if a.url:
            page = ctx.new_page()
            opened = True
            page.on("dialog", lambda d: d.dismiss())
            net = NetCapture(page) if a.net else None
            page.goto(a.url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            run.step("open", url=a.url[:160])
            if es.is_eclass(a.url):
                st = wait_session(page, run, a.wait_user, a.ea_name)
                if st["state"] in es.WAIT_USER_STATES and a.wait_user > 0:
                    return emit({"ok": False, "action": "snapshot", "port": port, "state": st["state"],
                                 "url": (st.get("url") or "")[:200], "hint": "사용자 조치 후 재실행(탭 유지)",
                                 "out": str(run.dir)}, EXIT_WAIT_USER)
        else:
            cands = list(ctx.pages)
            if a.tab:
                needle = a.tab.lower()
                cands = [pg for pg in cands if needle in ch.page_url(pg).lower()
                         or needle in (pg.title() or "").lower()]
            else:
                order = {"docview": 0, "eapproval": 1, "loginbyname": 2, "eclass": 3, "msgbox": 4, "login": 5, "other": 6}
                cands = sorted(cands, key=lambda pg: order.get(es.tab_kind(ch.page_url(pg)), 9))
                cands = [pg for pg in cands if es.tab_kind(ch.page_url(pg)) == es.tab_kind(ch.page_url(cands[0]))] if cands else []
            if not cands:
                return emit({"ok": False, "action": "snapshot", "port": port, "state": "no_tab",
                             "tabs": es.tab_summary(ch.page_targets(port)),
                             "hint": "대상 탭 없음 — --tab 부분문자열 또는 --url 지정"}, EXIT_MISSING)
            page = cands[-1]
            if a.net:
                net = NetCapture(page)
                page.wait_for_timeout(int(a.net_seconds * 1000))
        inv.wait_form_ready(page, polls=a.polls if a.url else 3)
        summary = inventory_page(page, run, a.form_id, net)
        closed = close_if(page, opened, a.keep)
        result = {"ok": summary["fields"] > 0, "action": "snapshot", "port": port, **summary,
                  "opened_tab": opened, "closed_tab": closed, "out": str(run.dir)}
        if summary["fields"] == 0:
            result["error"] = "PROBE_EMPTY"
            result["hint"] = "수집 필드 0건 — 대상 탭/프레임 확인(shot.png)"
            return emit(result, EXIT_EMPTY)
        result["hint"] = ("fieldmap.draft.yaml 검토 후 recipe 승격" if summary["draft"]
                          else "편집 가능 컨트롤 없음 — 목록/조회 화면이면 inventory.json 만 참고")
        return emit(result, EXIT_OK)


def act_draft(a) -> int:
    if not a.inventory:
        return emit({"ok": False, "action": "draft", "error": "--inventory 경로 필요"}, EXIT_ERR)
    src = Path(a.inventory)
    if not src.exists():
        return emit({"ok": False, "action": "draft", "error": f"파일 없음: {src}"}, EXIT_MISSING)
    inventory = json.loads(src.read_text(encoding="utf-8"))
    text = inv.fieldmap_draft(inventory, a.form_id, str(src))
    out = Path(a.out) if a.out else src.with_name("fieldmap.draft.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    fr = inv.pick_form_frame(inventory.get("frames") or []) or {}
    return emit({"ok": True, "action": "draft", "inventory": str(src), "out": str(out),
                 "form_id": a.form_id or inventory.get("form_id"), "form_frame": (fr.get("url") or "")[:120],
                 "lines": text.count("\n"), "hint": "초안 — 검증 전 러너 사용 금지"}, EXIT_OK)


# ── CLI ───────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="eclass 전자결재 정탐(읽기 전용)", add_help=False)
    ap.add_argument("action", nargs="?", default="help",
                    choices=["status", "forms", "form", "snapshot", "draft", "help", "-h", "--help"])
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--env", default=None, help="KEY=VALUE 파일(기본: 프로젝트 루트 .env.eclass 가 있으면)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep", action="store_true", help="이 실행이 연 탭을 닫지 않는다")
    ap.add_argument("--net", action="store_true", help="XHR/fetch/document 요청·응답 요약 캡처")
    ap.add_argument("--net-seconds", type=float, default=5.0, help="snapshot(기존 탭)에서 --net 캡처 시간")
    ap.add_argument("--wait-user", type=int, default=45, help="로그인·성명 등 사용자 조치 대기(초)")
    ap.add_argument("--ea-name", default=None, help="RealEANet 성명 핸드셰이크 자동 입력(기본 KRS_EA_NAME/ECLASS_EA_NAME)")
    ap.add_argument("--polls", type=int, default=40, help="폼 준비 폴링 횟수(400ms 간격)")
    ap.add_argument("--form-id", default=None)
    ap.add_argument("--url", default=None)
    ap.add_argument("--tab", default=None, help="snapshot 대상 탭(URL/제목 부분문자열)")
    ap.add_argument("--inventory", default=None, help="draft 입력 inventory.json")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.action in ("help", "-h", "--help"):
        print(HELP)
        return EXIT_OK
    env_path = Path(a.env) if a.env else (ROOT / ".env.eclass")
    loaded = load_env(env_path)
    a.port = es.resolve_port(a.port)
    if not a.ea_name:
        a.ea_name = os.environ.get("KRS_EA_NAME") or os.environ.get("ECLASS_EA_NAME") or None
    try:
        return {"status": act_status, "forms": act_forms, "form": act_form,
                "snapshot": act_snapshot, "draft": act_draft}[a.action](a)
    except Exception as e:  # noqa: BLE001
        return emit({"ok": False, "action": a.action, "port": a.port, "error": f"{type(e).__name__}: {str(e)[:300]}",
                     "env_keys": loaded, "hint": "채널 생존(status)·playwright 설치·URL 을 확인"}, EXIT_ERR)


if __name__ == "__main__":
    sys.exit(main())

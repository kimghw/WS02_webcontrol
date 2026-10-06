"""ea_core.eclass_inventory — eclass 전자결재 전용 인벤토리 확장: 결재양식함 카탈로그 · 폼/툴바 프레임 · fieldmap 초안 어댑터.

역할 한 줄: 범용 인벤토리(web_core.page_inventory) 위에 eclass(RealEANet) 화면 지식을 얹는다.
주요 기능:
- CATALOG_JS / parse_open_app_doc_win / dedupe_forms / assign_categories: 결재양식함(SelectBaseFormTypeB.aspx)의
  OpenAppDocWin('…DocumentView.aspx?FORMID=…') 링크 → {label, form_id, url, category} 카탈로그.
- toolbar_frame · form_frame(제목 앵커) · catalog_frame · wait_form_ready — DocumentView 프레임 판별.
- pick_form_frame(제목 앵커 우선) · fieldmap_draft(inventory, form_id, source): 범용 초안에 eclass 진입(open: loginbyname 경유)·
  제목 필드·DEXT5 본문 편집기·툴바(저장/상신 버튼 위치) 절을 붙인다. **러너 정본이 아니다** — 검증 후 recipe 로 승격.
범용 부분(INVENTORY_JS·scan_frames·frame_with·wait_for·detect_prefix·field_key·yq 등)은 web_core.page_inventory 를
그대로 다시 내보낸다(복사 금지 — import 만). playwright 를 import 하지 않는다(순수 함수는 ea_core/tests 로 검증).
검색 키워드: 결재양식함, OpenAppDocWin, FORMID, 카탈로그, DocumentView, 툴바, 제목 앵커, DEXT5, fieldmap 초안, 정탐.
"""
from __future__ import annotations

import re
from collections import OrderedDict

from web_core import page_inventory as _pi
from web_core.page_inventory import (INVENTORY_JS, BUTTON_TYPES, detect_prefix, editable, field_key,  # noqa: F401
                                     frame_name, frame_url, frame_with, has_selector, scan_frames, total_fields,
                                     wait_for, yq)

from .eclass_session import SEL, build_document_url

CATALOG_JS = r"""
() => {
  const clip = (s, n) => (s || '').toString().replace(/\s+/g, ' ').trim().slice(0, n);
  const tabs = [...document.querySelectorAll('a[id*="rtsCategorys_ctl"]')].map(a => ({ id: a.id, text: clip(a.innerText, 40) }));
  const forms = [];
  for (const a of document.querySelectorAll('a[onclick*="OpenAppDocWin"]')) {
    const text = clip(a.innerText, 80); if (!text) continue;
    const r = a.getBoundingClientRect();
    forms.push({ label: text, onclick: a.getAttribute('onclick') || '', visible: r.width > 0 && r.height > 0,
      container: (a.closest('div[id],table[id]') || {}).id || null });
  }
  return { title: document.title, url: location.href, tabs, forms };
}
"""

_OPEN_RE = re.compile(r"OpenAppDocWin\(\s*'([^']+)'", re.I)
_FORMID_RE = re.compile(r"FORMID=([^&'\"\s]+)", re.I)


# ── 카탈로그 파싱(순수) ───────────────────────────────────────────────
def parse_open_app_doc_win(onclick: str) -> dict | None:
    """onclick="javascript:return OpenAppDocWin('/RealEANET/Main/DocumentView.aspx?FORMID=X&…')" → {url, form_id}."""
    m = _OPEN_RE.search(onclick or "")
    if not m:
        return None
    url = m.group(1)
    f = _FORMID_RE.search(url)
    return {"url": url, "form_id": f.group(1) if f else None}


def dedupe_forms(raw_forms: list[dict]) -> list[dict]:
    """CATALOG_JS 결과의 forms 를 form_id 기준으로 유일화(라벨 있는 첫 항목 유지)."""
    seen: dict[str, dict] = OrderedDict()
    for f in raw_forms or []:
        parsed = parse_open_app_doc_win(f.get("onclick") or "")
        if not parsed or not parsed["form_id"]:
            continue
        fid = parsed["form_id"]
        if fid in seen:
            if not seen[fid]["visible"] and f.get("visible"):
                seen[fid]["visible"] = True
            continue
        seen[fid] = {"form_id": fid, "label": f.get("label") or "", "visible": bool(f.get("visible")),
                     "container": f.get("container"), "url": parsed["url"]}
    return list(seen.values())


def assign_categories(forms: list[dict], tabs: list[dict]) -> list[dict]:
    """container(등장 순) ↔ 카테고리 탭(등장 순) 대응으로 category 부여. 개수가 다르면 None(휴리스틱)."""
    containers: list[str] = []
    for f in forms:
        c = f.get("container")
        if c and c not in containers:
            containers.append(c)
    names = [t.get("text") for t in (tabs or [])]
    mapping = dict(zip(containers, names)) if containers and len(containers) == len(names) else {}
    for f in forms:
        f["category"] = mapping.get(f.get("container"))
    return forms


# ── eclass 프레임 판별(라이브 — page/frame 객체는 인자로만) ──────────────
def toolbar_frame(page):
    return next((f for f in page.frames
                 if "toolbar" in frame_url(f).lower() or "toolbar" in frame_name(f).lower()), None)


def form_frame(page):
    return frame_with(page, SEL["form_title"])


def catalog_frame(page):
    return next((f for f in page.frames if "selectbaseformtype" in frame_url(f).lower()), None)


def wait_form_ready(page, polls: int = 40, interval_ms: int = 400) -> dict:
    """toolbar frame 또는 폼 본체 앵커가 나타날 때까지 대기. {ready, toolbar, form}."""
    def _pred():
        return (toolbar_frame(page) is not None) or (form_frame(page) is not None)
    wait_for(page, _pred, polls, interval_ms)
    return {"ready": bool(_pred()), "toolbar": toolbar_frame(page) is not None, "form": form_frame(page) is not None}


# ── fieldmap 초안 어댑터(순수) ─────────────────────────────────────────
TITLE_ID = SEL["form_title"].lstrip("#")


def pick_form_frame(frames: list[dict]) -> dict | None:
    """폼 본체 프레임: 제목 앵커(SEL.form_title)를 가진 프레임 > 편집 가능 컨트롤이 가장 많은 프레임."""
    return _pi.pick_form_frame(frames, TITLE_ID)


def _open_lines(fid: str) -> list[str]:
    if not fid:
        return []
    doc = build_document_url(fid)
    return ["open:",
            f"  url: {yq(doc.split('?', 1)[0])}",
            f"  query: {yq(doc.split('?', 1)[1])}",
            "  entry: \"loginbyname.aspx?ReturnUrl=<위 경로+쿼리> 경유(references/eclass/eclass_eapproval_tour.md)\""]


def _tail_lines(frames: list[dict]) -> list[str]:
    L: list[str] = []
    editor_frames = [f2.get("index") for f2 in frames if (f2.get("editors") or {}).get("dext_body")]
    L.append("")
    L.append("editor:   # 본문 편집기(DEXT5 #dext_body) — DSL v1 primitive 밖. 본문 주입은 별도 core 모듈/hook 후보")
    L.append(f"  dext_body_frames: [{', '.join(str(i) for i in editor_frames)}]")
    toolbar_frs = [f2 for f2 in frames
                   if "toolbar" in ((f2.get("name") or "") + " " + (f2.get("url") or "")).lower()]
    L.append("")
    L.append("toolbar:   # 저장·상신 버튼 위치(참고용 — 클릭 금지). 임시저장은 러너 게이트 뒤에서만, 상신은 사용자 직접")
    if not toolbar_frs:
        L.append("  frame: null   # toolbar 프레임 미발견")
    for tf in toolbar_frs[:1]:
        L.append(f"  frame: {yq(((tf.get('name') or '') + ' | ' + (tf.get('url') or ''))[:160])}")
        tb = [b for b in tf.get("fields") or [] if _pi.is_button(b)]
        L.append("  buttons:" + ("" if tb else " []"))
        for b in tb[:40]:
            L.append(f"    - {{id: {yq(b.get('id') or '')}, text: {yq(b.get('text') or '')}, title: {yq(b.get('title') or b.get('label') or '')}, visible: {str(bool(b.get('visible'))).lower()}}}")
    return L


def fieldmap_draft(inventory: dict, form_id: str | None = None, source: str = "") -> str:
    """inventory.json(dict) → eclass 폼 fieldmap DSL v1 초안 YAML 텍스트(범용 골격 + eclass 절)."""
    frames = inventory.get("frames") or []
    fid = form_id or inventory.get("form_id") or ""
    return _pi.fieldmap_draft(inventory, form_id=fid, source=source, frame=pick_form_frame(frames),
                              anchor=SEL["form_title"], title_id=TITLE_ID, generator="probes/ea_eclass_probe.py",
                              open_lines=_open_lines(fid) or None, extra_lines=_tail_lines(frames))


__all__ = ["INVENTORY_JS", "CATALOG_JS", "parse_open_app_doc_win", "dedupe_forms", "assign_categories",
           "toolbar_frame", "form_frame", "catalog_frame", "wait_form_ready", "pick_form_frame", "fieldmap_draft",
           "TITLE_ID", "scan_frames", "total_fields", "frame_with", "frame_url", "frame_name", "wait_for",
           "detect_prefix", "field_key", "editable", "yq"]

"""web_core.page_inventory — 프레임·컨트롤 인벤토리(JS) · 프레임 도우미 · fieldmap DSL v1 초안(범용 골격).

역할 한 줄: 어느 사이트든 "화면에 무엇이 있나"를 JSON 으로 뽑고, 그것을 fieldmap DSL v1 초안(YAML 텍스트)으로 바꾼다.
주요 기능:
- INVENTORY_JS / scan_frames(page): 프레임마다 컨트롤(id·name·type·label·options·visible·disabled·maxlength),
  포스트백·onclick 앵커, iframe, 입력 테이블(헤더), 위젯 힌트(contenteditable·DEXT·RadDatePicker·canvas·__doPostBack).
- frame helpers: has_selector · frame_url · frame_name · frame_with · wait_for · wait_selector
  (postback 후 프레임 핸들이 stale 해지므로 매번 재탐색 = frame_reacquire).
- pick_form_frame · detect_prefix(ASP.NET ctl00_ 접두) · field_key(snake 키) · editable.
- fieldmap_draft(inventory, …): 컨트롤을 DSL v1 primitive(text·select·checkbox_enum·date_tab_commit·repeat_row,
  DSL 밖 radio_enum)로 분류한 초안 YAML 텍스트. 사이트 어댑터(그룹 core)는 frame·anchor·title_id·open_lines·extra_lines 로 확장한다.
  **러너 정본이 아니다** — 사용자 검토·canary 후 recipe(fieldmap.yaml)로 승격.
- draft_summary(text) 초안 primitive 개수 요약 · inventory_diff(before, after) 조작 전/후 컨트롤 증감(실연 비교).
브라우저 기동·클릭·입력 없음(evaluate 읽기만). playwright 를 import 하지 않는다(덕 타이핑 — 순수 함수는
web_core/tests/test_page_inventory.py 로 브라우저 없이 검증).
검색 키워드: 인벤토리, 필드 목록, 셀렉터 수집, fieldmap 초안, 프레임 재취득, 정탐, DSL v1, 조작 전후 비교.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict

# ── 브라우저에서 실행되는 JS(읽기 전용) ─────────────────────────────────
INVENTORY_JS = r"""
() => {
  const clip = (s, n) => (s || '').toString().replace(/\s+/g, ' ').trim().slice(0, n);
  const esc = (id) => (window.CSS && CSS.escape) ? CSS.escape(id) : id;
  const isVisible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const labelOf = (el) => {
    if (el.id) { const l = document.querySelector('label[for="' + esc(el.id) + '"]'); if (l && clip(l.innerText, 60)) return clip(l.innerText, 60); }
    const pl = el.closest('label'); if (pl && clip(pl.innerText, 60)) return clip(pl.innerText, 60);
    const al = el.getAttribute('aria-label'); if (al) return clip(al, 60);
    if (el.type === 'checkbox' || el.type === 'radio') {
      const n = el.nextSibling; if (n && n.nodeType === 3 && clip(n.textContent, 60)) return clip(n.textContent, 60);
      const ne = el.nextElementSibling; if (ne && (ne.tagName === 'LABEL' || ne.tagName === 'SPAN') && clip(ne.innerText, 60)) return clip(ne.innerText, 60);
    }
    const td = el.closest('td,th');
    if (td) {
      let prev = td.previousElementSibling;
      while (prev && !clip(prev.innerText, 60)) prev = prev.previousElementSibling;
      if (prev && clip(prev.innerText, 60)) return clip(prev.innerText, 60);
      const tr = td.closest('tr');
      if (tr && tr.cells.length && tr.cells[0] !== td && clip(tr.cells[0].innerText, 60)) return clip(tr.cells[0].innerText, 60);
      const table = td.closest('table');
      if (table && table.rows.length && td.cellIndex >= 0) {
        const h = table.rows[0].cells[td.cellIndex];
        if (h && h !== td && clip(h.innerText, 60)) return clip(h.innerText, 60);
      }
    }
    return clip(el.placeholder || el.title || '', 60);
  };
  const fields = []; let stateHidden = 0;
  for (const el of document.querySelectorAll('input,select,textarea,button')) {
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    if (tag === 'input' && type === 'hidden') {
      if ((el.name || el.id || '').startsWith('__')) { stateHidden++; continue; }
      fields.push({ tag, type, id: el.id || null, name: el.name || null, visible: false, hidden: true });
      continue;
    }
    const r = el.getBoundingClientRect();
    const f = { tag, type: type || null, id: el.id || null, name: el.name || null,
      visible: r.width > 0 && r.height > 0,
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      label: labelOf(el), disabled: !!el.disabled, readonly: !!el.readOnly,
      maxlength: (el.maxLength && el.maxLength > 0) ? el.maxLength : null,
      placeholder: el.placeholder || null, title: el.title || null, cls: clip(el.className, 60) || null };
    if (type === 'checkbox' || type === 'radio') { f.checked = !!el.checked; f.value = clip(el.value, 40); }
    if (tag === 'select') {
      f.options = [...el.options].slice(0, 60).map(o => ({ v: clip(o.value, 40), t: clip(o.text, 40) }));
      f.selected = clip(el.value, 40); f.multiple = !!el.multiple;
    }
    if (tag === 'button' || type === 'submit' || type === 'button' || type === 'image' || type === 'reset') {
      f.text = clip(el.innerText || el.value || el.alt, 40); f.onclick = clip(el.getAttribute('onclick'), 160) || null;
    }
    if (tag === 'textarea') f.rows = el.rows || null;
    if (type === 'file') f.accept = el.accept || null;
    fields.push(f);
  }
  const anchors = [...document.querySelectorAll('a')].map(a => {
    const href = a.getAttribute('href') || ''; const oc = a.getAttribute('onclick') || '';
    if (!(href.includes('__doPostBack') || oc || href.startsWith('javascript'))) return null;
    return { id: a.id || null, text: clip(a.innerText, 40), href: clip(href, 160), onclick: clip(oc, 160) || null, visible: isVisible(a) };
  }).filter(Boolean).slice(0, 200);
  const iframes = [...document.querySelectorAll('iframe,frame')].map(f => ({
    tag: f.tagName.toLowerCase(), id: f.id || null, name: f.name || null, src: clip(f.getAttribute('src'), 200), visible: isVisible(f) }));
  const tables = [...document.querySelectorAll('table')]
    .filter(t => t.querySelectorAll('input:not([type=hidden]),select,textarea').length > 0)
    .map(t => ({ id: t.id || null, rows: t.rows.length,
      inputs: t.querySelectorAll('input:not([type=hidden]),select,textarea').length,
      headers: t.rows.length ? [...t.rows[0].cells].slice(0, 12).map(c => clip(c.innerText, 30)) : [] })).slice(0, 60);
  const editors = { dext_body: !!document.querySelector('#dext_body'),
    contenteditable: document.querySelectorAll('[contenteditable=true]').length,
    rad_date_inputs: document.querySelectorAll('input[id$="_dateInput"]').length,
    canvas: document.querySelectorAll('canvas').length,
    telerik: !!(window.Telerik), dopostback: typeof window.__doPostBack === 'function' };
  return { title: document.title, url: location.href, readyState: document.readyState,
    counts: { fields: fields.length, state_hidden: stateHidden, anchors: anchors.length, iframes: iframes.length, tables: tables.length },
    fields, anchors, iframes, tables, editors, text: clip(document.body ? document.body.innerText : '', 300) };
}
"""

# ── frame helpers(라이브 — page/frame 객체는 인자로만) ───────────────────
def has_selector(fr, sel: str) -> bool:
    try:
        return fr.query_selector(sel) is not None
    except Exception:
        return False


def frame_url(fr) -> str:
    try:
        return fr.url or ""
    except Exception:
        return ""


def frame_name(fr) -> str:
    try:
        return fr.name or ""
    except Exception:
        return ""


def frame_with(page, sel: str):
    """셀렉터를 가진 첫 frame(없으면 None). postback 뒤에는 반드시 다시 부른다(frame_reacquire)."""
    return next((f for f in page.frames if has_selector(f, sel)), None)


def wait_for(page, pred, polls: int = 40, interval_ms: int = 400):
    """pred() 가 참(비None)이 될 때까지 짧은 간격 폴링(고정 sleep 금지). 마지막 값 반환."""
    val = None
    for _ in range(max(1, polls)):
        val = pred()
        if val:
            return val
        page.wait_for_timeout(interval_ms)
    return pred()


def wait_selector(page, sel: str, polls: int = 40, interval_ms: int = 400):
    """어느 frame 에든 sel 이 나타날 때까지 폴링. 그 frame(없으면 None)."""
    return wait_for(page, lambda: frame_with(page, sel), polls, interval_ms)


def scan_frames(page) -> list[dict]:
    """모든 frame 에 INVENTORY_JS 실행. 프레임별 {index,name,url,parent,…인벤토리} 또는 error."""
    out = []
    for i, fr in enumerate(page.frames):
        entry = {"index": i, "name": frame_name(fr), "url": frame_url(fr)[:300],
                 "parent": frame_url(fr.parent_frame)[:120] if fr.parent_frame else None}
        try:
            entry.update(fr.evaluate(INVENTORY_JS))
        except Exception as e:  # noqa: BLE001
            entry["error"] = str(e)[:200]
            entry["fields"] = []
        out.append(entry)
    return out


def total_fields(frames: list[dict]) -> int:
    return sum(len(f.get("fields") or []) for f in frames)


# ── 분류(순수) ────────────────────────────────────────────────────────
BUTTON_TYPES = {"submit", "button", "image", "reset"}


def editable(f: dict) -> bool:
    """값을 넣을 수 있는 컨트롤인가(hidden·버튼 제외)."""
    if f.get("hidden"):
        return False
    if f.get("tag") not in ("input", "select", "textarea"):
        return False
    return (f.get("type") or "") not in BUTTON_TYPES


def is_button(f: dict) -> bool:
    return (f.get("type") or "") in BUTTON_TYPES or f.get("tag") == "button"


def pick_form_frame(frames: list[dict], anchor_id: str | None = None) -> dict | None:
    """폼 본체 프레임: anchor_id 컨트롤을 가진 프레임 > 보이는 편집 가능 컨트롤이 가장 많은 프레임."""
    if anchor_id:
        for fr in frames:
            if any((f.get("id") == anchor_id) for f in fr.get("fields") or []):
                return fr
    best, best_n = None, 0
    for fr in frames:
        n = sum(1 for f in fr.get("fields") or [] if editable(f) and f.get("visible"))
        if n > best_n:
            best, best_n = fr, n
    return best


def detect_prefix(ids: list[str]) -> str:
    """ASP.NET 컨트롤 id 공통 접두(예: ctl00_ContentPlaceHolder_Content_). 2개 이상 공유할 때만."""
    cands = Counter()
    for i in ids:
        if i and "_" in i and i.startswith("ctl00_"):
            cands[i.rsplit("_", 1)[0] + "_"] += 1
    # repeater/enum 꼬리(…_ctl01_, …_0_) 를 접두로 잡지 않도록 짧은 쪽을 우선
    best = ""
    for cand, n in cands.most_common():
        if n < 2:
            break
        if re.search(r"_ctl\d{2}_$|_\d+_$", cand):
            continue
        if not best or (n >= cands[best] and len(cand) < len(best)):
            best = cand
    return best


def field_key(tail: str, used: set[str]) -> str:
    t = re.sub(r"^(txt|ddl|chk|cbl|rbl|rdo|rad|dtp|tb|lst|cb|fu)(?=[A-Z_])", "", tail or "")
    t = re.sub(r"(?<!^)(?=[A-Z])", "_", t).lower()
    t = re.sub(r"[^a-z0-9_]+", "_", t).strip("_")
    t = re.sub(r"_+", "_", t) or "field"
    base, n = t, 2
    while t in used:
        t = f"{base}_{n}"
        n += 1
    used.add(t)
    return t


def yq(s) -> str:
    """YAML 안전 문자열(항상 큰따옴표)."""
    s = "" if s is None else str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def css_id(cid: str) -> str:
    """id → CSS 셀렉터. CSS 식별자로 못 쓰는 문자(:, ., 숫자 시작 등)가 있으면 속성 셀렉터."""
    if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", cid or ""):
        return "#" + cid
    return '[id="' + (cid or "").replace('"', '\\"') + '"]'


# ── fieldmap 초안(순수) ───────────────────────────────────────────────
def fieldmap_draft(inventory: dict, *, form_id: str | None = None, source: str = "",
                   frame: dict | None = None, anchor: str | None = None, title_id: str | None = None,
                   generator: str = "probes/web_probe.py", open_lines: list[str] | None = None,
                   extra_lines: list[str] | None = None) -> str:
    """inventory.json(dict) → fieldmap DSL v1 초안 YAML 텍스트. 러너 정본 아님(검증 후 recipe 로 승격).

    사이트 어댑터 확장점: frame(폼 프레임 강제) · anchor(frame_reacquire 앵커 셀렉터) · title_id(제목 컨트롤 id —
    fields.title 로 고정) · open_lines(`open:` 절 등 진입 정보 YAML 줄) · extra_lines(꼬리 절 — 편집기·툴바 등).
    """
    frames = inventory.get("frames") or []
    anchor_id = anchor.lstrip("#") if anchor and anchor.startswith("#") else None
    fr = frame or pick_form_frame(frames, anchor_id) or {}
    fields = [f for f in fr.get("fields") or [] if editable(f)]
    anchors = fr.get("anchors") or []
    ids = [f.get("id") for f in fields if f.get("id")]
    prefix = detect_prefix(ids)
    fid = form_id or inventory.get("form_id") or ""
    ts = inventory.get("ts") or ""
    used: set[str] = set()
    anchor_guess = False
    if not anchor:
        first = next((f for f in fields if f.get("id") and f.get("visible")), None)
        if first:
            anchor, anchor_guess = css_id(first["id"]), True

    def sel_of(cid: str) -> str:
        if prefix and cid.startswith(prefix):
            return "{prefix}" + cid[len(prefix):]
        return css_id(cid)

    def tail_of(cid: str) -> str:
        return cid[len(prefix):] if prefix and cid.startswith(prefix) else cid

    simple: list[tuple[str, dict]] = []     # (key, spec)
    enums: "OrderedDict[str, dict]" = OrderedDict()   # base → {type, items:[(idx,label,id)]}
    repeats: "OrderedDict[str, dict]" = OrderedDict() # base → {rows:set, cells:OrderedDict(cell→label)}
    attachments: list[dict] = []
    hooks: list[dict] = []
    unmapped: list[dict] = []
    title_seen = False

    for f in fields:
        cid = f.get("id") or ""
        typ = (f.get("type") or "").lower()
        tag = f.get("tag")
        label = f.get("label") or ""
        if not cid:
            unmapped.append({"name": f.get("name"), "tag": tag, "type": typ, "label": label})
            continue
        if title_id and cid == title_id:
            title_seen = True
            continue
        tail = tail_of(cid)
        m_rep = re.match(r"^(.*?)_ctl(\d{2})_(.+)$", tail)
        m_enum = re.match(r"^(.*?)_(\d+)$", tail)
        if m_rep:
            base, nn, cell = m_rep.group(1), int(m_rep.group(2)), m_rep.group(3)
            g = repeats.setdefault(base, {"rows": set(), "cells": OrderedDict()})
            g["rows"].add(nn)
            if cell not in g["cells"]:
                g["cells"][cell] = label
            continue
        if typ in ("checkbox", "radio") and m_enum:
            base, idx = m_enum.group(1), int(m_enum.group(2))
            g = enums.setdefault(base, {"type": typ, "items": []})
            g["items"].append((idx, label, cid))
            continue
        if typ == "file":
            attachments.append({"id": cid, "selector": sel_of(cid), "label": label, "accept": f.get("accept")})
            continue
        if tail.endswith("_dateInput"):
            simple.append((field_key(tail[:-len("_dateInput")], used),
                           {"primitive": "date_tab_commit", "selector": sel_of(cid), "label": label}))
            continue
        if tag == "select":
            opts = [o.get("t") for o in f.get("options") or []]
            simple.append((field_key(tail, used),
                           {"primitive": "select", "selector": sel_of(cid), "label": label, "options": opts}))
            continue
        if tag == "textarea" or typ in ("text", "number", "tel", "email", "url", "search", "date", ""):
            spec = {"primitive": "text", "selector": sel_of(cid), "label": label}
            if tag == "textarea":
                spec["note"] = "textarea"
            if f.get("maxlength"):
                spec["maxlength"] = f["maxlength"]
            if f.get("readonly"):
                spec["note"] = (spec.get("note", "") + " readonly(팝업/계산값 후보)").strip()
            simple.append((field_key(tail, used), spec))
            continue
        hooks.append({"id": cid, "tag": tag, "type": typ, "label": label, "reason": "DSL v1 primitive 밖"})

    add_anchor_cands = [a for a in anchors if "__doPostBack" in (a.get("href") or "")
                        and (("추가" in (a.get("text") or "")) or "LinkButton" in (a.get("id") or "")
                             or "add" in (a.get("id") or "").lower())]
    buttons = [f for f in fr.get("fields") or [] if is_button(f)]

    L: list[str] = []
    L.append(f"# 폼 필드맵 초안(draft) — {generator} 가 inventory 에서 자동 생성. 러너가 읽는 정본이 아니다.")
    L.append("# 사용자 감독 canary 로 검증하기 전에는 recipe(fieldmap.yaml)로 승격하지 않는다. DSL v1 primitive:")
    L.append("#   text | select | checkbox_enum | date_tab_commit | repeat_row | frame_reacquire | calc_field | postcondition")
    L.append("#   — 목록 밖 위젯은 hooks_후보 에 남겼다. source: TODO 는 input.template.yaml 키로 바꾼다.")
    L.append(f"# 출처: {source or '(inventory)'} (실측 {ts}, form_id {fid or '?'})")
    L.append("dsl_version: 1")
    L.append("draft: true")
    L.append(f"form_id: {yq(fid)}")
    if inventory.get("url") and not open_lines:
        L.append("open:")
        L.append(f"  url: {yq((inventory.get('url') or '')[:300])}   # 실측 시 URL — 진입 경로는 context.md 에서 확정")
    for line in open_lines or []:
        L.append(line)
    L.append("frame:")
    L.append("  primitive: frame_reacquire")
    if anchor:
        L.append(f"  anchor: {yq(anchor)}" + ("   # 후보(첫 입력 컨트롤) — 폼에 늘 있는 고정 컨트롤로 확정할 것" if anchor_guess
                                            else ("" if (title_seen or not title_id) else "   # 주의: 이 인벤토리에서 앵커 미발견 — 프레임 앵커를 직접 정할 것")))
    else:
        L.append("  anchor: TODO   # 주의: 이 인벤토리에서 앵커 미발견 — 프레임 앵커를 직접 정할 것")
    L.append(f"  frame_url: {yq((fr.get('url') or '')[:200])}")
    L.append(f"  frame_index: {fr.get('index', 0)}")
    L.append(f"prefix: {yq('#' + prefix if prefix else '')}   # 폼 본체 컨트롤 공통 접두({{prefix}} 치환)")
    L.append("")
    L.append("fields:")
    if title_seen:
        L.append("  title:")
        L.append("    primitive: text")
        L.append(f"    selector: {yq(css_id(title_id))}   # 제목(접두 밖 — 폼 공통)")
        L.append("    source: fields.title")
        L.append("    required: true")
    for key, spec in simple:
        L.append(f"  {key}:")
        L.append(f"    primitive: {spec['primitive']}")
        L.append(f"    selector: {yq(spec['selector'])}   # 라벨: {spec.get('label') or '-'}")
        if spec.get("options") is not None:
            L.append(f"    options: [{', '.join(yq(o) for o in spec['options'][:20])}]")
        if spec.get("maxlength"):
            L.append(f"    maxlength: {spec['maxlength']}")
        if spec.get("note"):
            L.append(f"    note: {yq(spec['note'])}")
        L.append("    source: TODO")
    for base, g in enums.items():
        key = field_key(base, used)
        items = sorted(g["items"], key=lambda x: x[0])
        enum_txt = ", ".join(f"{yq(lbl or f'opt{idx}')}: {idx}" for idx, lbl, _ in items)
        L.append(f"  {key}:")
        if g["type"] == "checkbox":
            L.append("    primitive: checkbox_enum")
        else:
            L.append("    primitive: radio_enum   # DSL v1 밖(hooks 또는 primitive 승격 판단)")
        L.append(f"    selector: {yq(sel_of(items[0][2]).rsplit('_', 1)[0] + '_{index}')}")
        L.append(f"    enum: {{{enum_txt}}}")
        L.append("    source: TODO")
    if not simple and not enums and not title_seen:
        L.append("  {}   # 편집 가능 컨트롤을 찾지 못함 — 폼 미로딩/프레임 선택 확인")
    L.append("")
    L.append("repeat_rows:")
    if not repeats:
        L.append("  {}")
    for base, g in repeats.items():
        key = field_key(base, used)
        cells = list(g["cells"].items())
        first_cell = cells[0][0] if cells else "txt"
        cand = add_anchor_cands[0] if add_anchor_cands else None
        L.append(f"  {key}:")
        L.append("    primitive: repeat_row")
        L.append("    source: TODO")
        if cand:
            L.append(f"    add_anchor: {yq(sel_of(cand['id']) if cand.get('id') else cand.get('href'))}   # 후보: '{cand.get('text')}' — 어느 표의 행추가인지 확인 필요")
        else:
            L.append("    add_anchor: TODO   # __doPostBack 행추가 앵커 미발견")
        row_probe = "input[id*='" + base + "_ctl'][id$='" + first_cell + "']"
        L.append(f"    row_probe: {yq(row_probe)}")
        L.append(f"    cell_selector: {yq(('{prefix}' if prefix else '#') + base + '_ctl{nn}_{cell}')}")
        L.append("    cells:")
        for cell, lbl in cells:
            L.append(f"      {field_key(cell, set())}: {cell}   # {lbl or '-'}")
        L.append("    postback: full   # 확인 필요(행추가가 full postback 이면 frame_reacquire + 행 등장 폴링)")
        L.append(f"    observed_rows: {len(g['rows'])}")
    L.append("")
    L.append("attachments:" + ("" if attachments else " []"))
    for a in attachments:
        L.append(f"  - {{selector: {yq(a['selector'])}, label: {yq(a['label'])}, accept: {yq(a.get('accept') or '')}}}")
    L.append("")
    L.append("hooks_후보:" + ("" if (hooks or unmapped) else " []"))
    for h in hooks:
        L.append(f"  - {{id: {yq(h['id'])}, tag: {h['tag']}, type: {yq(h['type'])}, label: {yq(h['label'])}, reason: {yq(h['reason'])}}}")
    for u in unmapped:
        L.append(f"  - {{name: {yq(u['name'])}, tag: {u['tag']}, type: {yq(u['type'])}, label: {yq(u['label'])}, reason: \"id 없음(name 셀렉터 필요)\"}}")
    L.append("")
    L.append("buttons:   # 폼 프레임 안 버튼(참고용 — 정탐·러너 모두 저장/제출 클릭 금지)" + ("" if buttons else " []"))
    for b in buttons[:40]:
        L.append(f"  - {{id: {yq(b.get('id') or '')}, text: {yq(b.get('text') or '')}, visible: {str(bool(b.get('visible'))).lower()}}}")
    widget_frames = [(f2.get("index"), f2.get("editors") or {}) for f2 in frames]
    rich = [(i, e) for i, e in widget_frames
            if e.get("contenteditable") or e.get("dext_body") or e.get("canvas") or e.get("rad_date_inputs")]
    L.append("")
    L.append("widgets:   # DSL v1 밖일 수 있는 위젯 힌트(본문 편집기·canvas·달력) — core 모듈/hook 후보" + ("" if rich else " []"))
    for i, e in rich:
        L.append(f"  - {{frame_index: {i}, contenteditable: {e.get('contenteditable') or 0}, dext_body: "
                 f"{str(bool(e.get('dext_body'))).lower()}, canvas: {e.get('canvas') or 0}, rad_date_inputs: {e.get('rad_date_inputs') or 0}}}")
    for line in extra_lines or []:
        L.append(line)
    L.append("")
    L.append("postconditions:")
    if title_seen:
        L.append("  - {primitive: postcondition, check: \"fields.title 비어있지 않음\"}")
    else:
        L.append("  - {primitive: postcondition, check: \"TODO — 저장 후 확인할 조건(문서번호·성공 메시지 등)\"}")
    if repeats:
        L.append("  - {primitive: postcondition, check: \"repeat_row 확보 행 수 == 요청 행 수 (shortfall=0)\"}")
    L.append("")
    return "\n".join(L)


_PRIMS = ("text", "select", "checkbox_enum", "radio_enum", "date_tab_commit", "repeat_row")


def draft_summary(text: str) -> dict:
    """초안 YAML 텍스트의 primitive 개수 + hooks_후보 수 + 위젯 힌트 유무(보고용)."""
    out = {p: len(re.findall(rf"^\s+primitive: {p}\b", text, flags=re.M)) for p in _PRIMS}
    m = re.search(r"^hooks_후보:(.*?)(?=^\S)", text + "\nend:", flags=re.M | re.S)
    out["hooks"] = len(re.findall(r"^\s+- ", m.group(1), flags=re.M)) if m else 0
    out["widgets"] = not re.search(r"^widgets:.*\[\]\s*$", text, flags=re.M)
    return out


def _field_sig(fr: dict, f: dict) -> str:
    return f"{fr.get('index')}|{f.get('id') or ''}|{f.get('name') or ''}|{f.get('tag')}|{f.get('type') or ''}"


def inventory_diff(before: dict, after: dict) -> dict:
    """조작 전/후 인벤토리 비교 — 늘어난/사라진 컨트롤(행추가 postback·팝업 결과 등 실연 분석용)."""
    def sigs(inv: dict) -> dict:
        out = {}
        for fr in inv.get("frames") or []:
            for f in fr.get("fields") or []:
                out[_field_sig(fr, f)] = {"frame": fr.get("index"), "id": f.get("id"), "name": f.get("name"),
                                          "tag": f.get("tag"), "type": f.get("type"), "label": f.get("label")}
        return out
    b, a = sigs(before), sigs(after)
    return {"added": [a[k] for k in a if k not in b], "removed": [b[k] for k in b if k not in a],
            "frames_before": len(before.get("frames") or []), "frames_after": len(after.get("frames") or [])}


__all__ = ["INVENTORY_JS", "has_selector", "frame_url", "frame_name", "frame_with", "wait_for", "wait_selector",
           "scan_frames", "total_fields", "BUTTON_TYPES", "editable", "is_button", "pick_form_frame",
           "detect_prefix", "field_key", "yq", "css_id", "fieldmap_draft", "draft_summary", "inventory_diff"]

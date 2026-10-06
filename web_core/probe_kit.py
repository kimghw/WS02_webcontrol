"""web_core.probe_kit — 정탐(recon) 실행 키트: 출력 폴더·steps.jsonl · 요청/응답 캡처 · 사용자 실연(watch) 기록 · .env 로드.

역할 한 줄: 사이트와 무관하게 정탐 CLI(probes/*.py)가 공통으로 쓰는 실행 골격과 관찰 도구.
주요 기능:
- load_env(path) KEY=VALUE 파일을 os.environ 에 비덮어쓰기 주입(키 이름만 반환 — 값은 절대 출력하지 않는다)
- emit(obj, code) stdout JSON 1개 출력 · Run(출력 폴더 + steps.jsonl 1스텝 1행 + write_json/write_text)
- NetCapture(page) 요청/응답 요약(document·xhr·fetch·.aspx/.ashx/api). POST 본문은 기본 키 이름만
  (ASP.NET __EVENTTARGET/__EVENTARGUMENT 는 값까지 — postback 대상 식별용), values=True 일 때만 본문 원문.
  bodies=True 면 JSON/텍스트 응답 본문(20KB 이하)도 저장. 로그인 계열 URL 은 본문을 기록하지 않는다.
- Recorder(ctx) 사용자 실연 캡처 — 사용자가 직접 클릭·입력·제출하는 동안 이벤트(click/change/submit/Enter·Tab)와
  대상 컨트롤(id·name·type·라벨·CSS 셀렉터), 프레임/팝업/네비게이션, 다이얼로그를 기록. 입력값은 기본 마스킹
  (길이만), values=True 일 때만 원문. 스크립트 자신은 아무것도 클릭·입력하지 않는다(관찰만).
- close_if(page, opened, keep) 이 실행이 연 탭만 닫기.
검색 키워드: 정탐 키트, 실연 캡처, 사용자 조작 기록, watch, 네트워크 캡처, postback 본문, steps.jsonl, env 로드.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

NET_MAX = 600
BODY_MAX = 20000
EVENT_MAX = 3000


# ── 공통 유틸 ─────────────────────────────────────────────────────────
def load_env(path: Path | None) -> list[str]:
    """KEY=VALUE 파일을 os.environ 에 비덮어쓰기 주입. 읽은 키 이름만 반환(값은 절대 출력하지 않는다)."""
    keys: list[str] = []
    if not path or not Path(path).exists():
        return keys
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            keys.append(k)
    return keys


def emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    return code


def close_if(page, opened: bool, keep: bool) -> bool:
    if opened and not keep:
        try:
            page.close()
            return True
        except Exception:
            return False
    return False


class Run:
    """출력 폴더 + steps.jsonl(1스텝 1행). base 아래 <action>_<key>_<ts>/ (out 지정 시 그 폴더)."""

    def __init__(self, action: str, key: str, out: str | None, base: Path):
        self.ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (key or ""))[:60]
        self.dir = Path(out) if out else Path(base) / f"{action}_{safe}_{self.ts}"
        self._opened = False
        self.steps: list[dict] = []

    def ensure(self) -> Path:
        if not self._opened:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._opened = True
        return self.dir

    def step(self, name: str, **detail) -> None:
        row = {"ts": datetime.now().isoformat(timespec="seconds"), "step": name, **detail}
        self.steps.append(row)
        try:
            with (self.ensure() / "steps.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def write_json(self, name: str, obj) -> str:
        p = self.ensure() / name
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        return str(p)

    def write_text(self, name: str, text: str) -> str:
        p = self.ensure() / name
        p.write_text(text, encoding="utf-8")
        return str(p)


# ── 요청/응답 캡처 ─────────────────────────────────────────────────────
_SENSITIVE_URL = ("login", "logon", "signin", "auth", "password", "otp")
_EVENT_KEYS = ("__EVENTTARGET", "__EVENTARGUMENT")


def summarize_post(body: str | None, content_type: str = "", values: bool = False) -> dict | None:
    """POST 본문 요약: form-urlencoded 면 키 목록(+__EVENT* 값), 그 외는 길이만. values=True 면 원문(2000자)."""
    if not body:
        return None
    if values:
        return {"raw": body[:2000], "len": len(body)}
    ct = (content_type or "").lower()
    if "x-www-form-urlencoded" in ct or ("=" in body and "&" in body and not body.lstrip().startswith(("{", "["))):
        pairs = parse_qsl(body, keep_blank_values=True)
        keys = [k for k, _ in pairs if not k.startswith("__VIEWSTATE") and k not in ("__EVENTVALIDATION",)]
        out = {"keys": keys[:200], "n_keys": len(pairs), "len": len(body)}
        for k, v in pairs:
            if k in _EVENT_KEYS:
                out[k] = v[:200]
        return out
    if body.lstrip().startswith(("{", "[")):
        try:
            obj = json.loads(body)
            if isinstance(obj, dict):
                return {"json_keys": list(obj.keys())[:100], "len": len(body)}
        except Exception:
            pass
    return {"len": len(body)}


class NetCapture:
    """document/xhr/fetch(+.aspx/.ashx/api) 요청·응답 요약. attach(page) 로 여러 페이지(팝업 포함)에 붙인다."""

    def __init__(self, page=None, values: bool = False, bodies: bool = False):
        self.items: list[dict] = []
        self.values = values
        self.bodies = bodies
        self._t0 = time.time()
        if page is not None:
            self.attach(page)

    def attach(self, page) -> None:
        page.on("request", self._req)
        page.on("response", self._res)

    def _req(self, req):
        try:
            rtype = req.resource_type
            url = req.url or ""
            low = url.lower()
            if rtype not in ("xhr", "fetch", "document") and not any(k in low for k in (".aspx", ".ashx", "/api/")):
                return
            if len(self.items) >= NET_MAX:
                return
            post = None
            if req.method != "GET" and not any(k in low for k in _SENSITIVE_URL):
                try:
                    ct = (req.headers or {}).get("content-type", "")
                    post = summarize_post(req.post_data, ct, self.values)
                except Exception:
                    post = None
            frame = None
            try:
                frame = (req.frame.name or "") + " | " + (req.frame.url or "")[:100]
            except Exception:
                pass
            self.items.append({"t": round(time.time() - self._t0, 3), "method": req.method, "url": url[:300],
                               "type": rtype, "frame": frame, "post": post, "status": None, "content_type": None})
        except Exception:
            pass

    def _res(self, res):
        try:
            url = res.url or ""
            for it in reversed(self.items):
                if it["url"] == url[:300] and it["status"] is None:
                    it["status"] = res.status
                    ct = (res.headers or {}).get("content-type", "")[:80]
                    it["content_type"] = ct
                    if (self.bodies and it["type"] in ("xhr", "fetch") and not any(k in url.lower() for k in _SENSITIVE_URL)
                            and any(k in ct for k in ("json", "text", "xml", "javascript"))):
                        try:
                            body = res.text()
                            it["body"] = body[:BODY_MAX]
                            it["body_truncated"] = len(body) > BODY_MAX
                        except Exception as e:  # noqa: BLE001
                            it["body_error"] = str(e)[:80]
                    break
        except Exception:
            pass

    def posts(self) -> list[dict]:
        """POST 계열만(저장·조회 엔드포인트 후보)."""
        return [i for i in self.items if i["method"] != "GET"]


# ── 사용자 실연(watch) 기록 ─────────────────────────────────────────────
RECORDER_JS = r"""
(opts) => {
  // 옵션은 설치할 때마다 갱신(같은 탭에 이전 실행의 리스너가 남아 있어도 이번 실행 옵션을 따른다)
  window.__wcRecOpts = { values: !!(opts && opts.values) };
  if (window.__wcRecInstalled) return 'already';
  window.__wcRecInstalled = true;
  const clip = (s, n) => (s || '').toString().replace(/\s+/g, ' ').trim().slice(0, n);
  const esc = (id) => (window.CSS && CSS.escape) ? CSS.escape(id) : id;
  const labelOf = (el) => {
    if (el.id) { const l = document.querySelector('label[for="' + esc(el.id) + '"]'); if (l && clip(l.innerText, 60)) return clip(l.innerText, 60); }
    const pl = el.closest && el.closest('label'); if (pl && clip(pl.innerText, 60)) return clip(pl.innerText, 60);
    const al = el.getAttribute && el.getAttribute('aria-label'); if (al) return clip(al, 60);
    const td = el.closest && el.closest('td,th');
    if (td) { let p = td.previousElementSibling; while (p && !clip(p.innerText, 60)) p = p.previousElementSibling; if (p) return clip(p.innerText, 60); }
    return clip(el.placeholder || el.title || '', 60);
  };
  const cssPath = (el) => {
    if (el.id) return '#' + esc(el.id);
    const parts = [];
    let n = el;
    while (n && n.nodeType === 1 && parts.length < 5) {
      let s = n.tagName.toLowerCase();
      if (n.id) { parts.unshift('#' + esc(n.id) + (parts.length ? '' : '')); break; }
      if (n.name) s += '[name="' + n.name + '"]';
      else if (n.parentElement) {
        const sib = [...n.parentElement.children].filter(c => c.tagName === n.tagName);
        if (sib.length > 1) s += ':nth-of-type(' + (sib.indexOf(n) + 1) + ')';
      }
      parts.unshift(s);
      n = n.parentElement;
    }
    return parts.join(' > ');
  };
  const pick = (el) => {
    const c = el.closest ? el.closest('input,select,textarea,button,a,[onclick],[role=button],[contenteditable=true],label,td,li') : null;
    return c || el;
  };
  const desc = (el) => {
    const keepValues = !!(window.__wcRecOpts && window.__wcRecOpts.values);
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.type || '').toLowerCase();
    // text 는 컨트롤의 "이름표"만 — 입력값(value)·선택지 원문은 넣지 않는다(마스킹 계약)
    const isField = tag === 'select' || tag === 'textarea' || (tag === 'input' && !['button', 'submit', 'reset', 'image'].includes(type));
    const d = { tag, type: type || null, id: el.id || null, name: el.name || null, selector: cssPath(el),
      label: labelOf(el), text: isField || el.isContentEditable ? null : clip(el.innerText || el.value || el.alt || '', 40) };
    if (tag === 'a') { d.href = clip(el.getAttribute('href'), 160); }
    const oc = el.getAttribute && el.getAttribute('onclick'); if (oc) d.onclick = clip(oc, 160);
    if (type === 'checkbox' || type === 'radio') d.checked = !!el.checked;
    if (tag === 'select') { const o = el.options[el.selectedIndex]; d.selected_text = keepValues ? clip(o && o.text, 60) : null; d.selected_index = el.selectedIndex; }
    if (tag === 'input' || tag === 'textarea') {
      if (type === 'password') { d.value_len = (el.value || '').length; }
      else if (type !== 'checkbox' && type !== 'radio' && type !== 'button' && type !== 'submit') {
        d.value_len = (el.value || '').length; if (keepValues) d.value = clip(el.value, 120);
      }
    }
    if (el.isContentEditable) { d.value_len = (el.innerText || '').length; if (keepValues) d.value = clip(el.innerText, 120); }
    if (tag === 'button' || type === 'submit' || type === 'button') d.text = clip(el.innerText || el.value, 40);
    if (type === 'checkbox' || type === 'radio') d.value = clip(el.value, 40);   // 선택지 코드(입력값 아님)
    if (tag === 'label' || tag === 'td' || tag === 'li') d.text = clip(el.innerText, 40);
    return d;
  };
  const send = (kind, el, extra) => {
    try { window.__wcRec(Object.assign({ kind, url: location.href.slice(0, 200), target: desc(el) }, extra || {})); } catch (e) {}
  };
  document.addEventListener('click', (e) => send('click', pick(e.target)), true);
  document.addEventListener('change', (e) => send('change', e.target), true);
  document.addEventListener('submit', (e) => send('submit', e.target), true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === 'Tab') send('key', e.target, { key: e.key }); }, true);
  return 'installed';
}
"""


class Recorder:
    """사용자 실연 캡처. ctx(브라우저 컨텍스트)의 대상 페이지 + 이후 열리는 팝업/새 탭까지 관찰한다(관찰만 — 클릭·입력 없음)."""

    def __init__(self, ctx, values: bool = False, net: NetCapture | None = None, sink: Path | None = None):
        self.ctx = ctx
        self.values = values
        self.net = net
        self.sink = sink
        self.events: list[dict] = []
        self.pages: list = []
        self._t0 = time.time()
        self._seq = 0

    def _push(self, row: dict) -> None:
        if len(self.events) >= EVENT_MAX:
            return
        self._seq += 1
        row = {"seq": self._seq, "t": round(time.time() - self._t0, 3), **row}
        self.events.append(row)
        if self.sink is not None:
            try:
                with self.sink.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def page_index(self, page) -> int:
        try:
            return self.pages.index(page)
        except ValueError:
            return -1

    def _binding(self, source, payload):
        frame = source.get("frame") if isinstance(source, dict) else None
        page = source.get("page") if isinstance(source, dict) else None
        fname = ""
        try:
            fname = frame.name or ""
        except Exception:
            pass
        self._push({"kind": (payload or {}).get("kind"), "page": self.page_index(page), "frame": fname,
                    "url": (payload or {}).get("url"), "key": (payload or {}).get("key"),
                    "target": (payload or {}).get("target")})

    def watch(self, page) -> None:
        """page 에 기록기를 붙인다(현재 문서의 모든 frame + 이후 네비게이션)."""
        if page in self.pages:
            return
        self.pages.append(page)
        idx = len(self.pages) - 1
        try:
            page.expose_binding("__wcRec", self._binding)
        except Exception as e:  # noqa: BLE001  (이미 등록된 경우 등)
            self._push({"kind": "recorder_warn", "page": idx, "error": str(e)[:120]})
        opts = json.dumps({"values": self.values})
        try:
            page.add_init_script(f"({RECORDER_JS})({opts})")
        except Exception:
            pass
        self._install_frames(page)
        page.on("framenavigated", lambda fr: self._on_nav(page, fr))
        page.on("dialog", lambda d: self._push({"kind": "dialog", "page": self.page_index(page), "type": d.type,
                                                 "message": (d.message or "")[:200]}))
        page.on("close", lambda *_: self._push({"kind": "page_close", "page": self.page_index(page)}))
        if self.net is not None:
            self.net.attach(page)

    def _install_frames(self, page) -> None:
        for fr in page.frames:
            try:
                fr.evaluate(RECORDER_JS, {"values": self.values})
            except Exception:
                pass

    def _on_nav(self, page, fr) -> None:
        try:
            is_main = fr == page.main_frame
            self._push({"kind": "navigate", "page": self.page_index(page), "frame": fr.name or "",
                        "main": is_main, "url": (fr.url or "")[:200]})
        except Exception:
            pass

    def follow_new_pages(self) -> None:
        """이후 열리는 팝업/새 탭에도 기록기를 붙인다."""
        def _on_page(pg):
            self._push({"kind": "page_open", "page": len(self.pages), "url": (pg.url or "")[:200]})
            self.watch(pg)
        self.ctx.on("page", _on_page)

    def reinstall(self) -> None:
        """폴링 중 주기 호출 — init script 가 닿지 않은 frame(about:blank 후 document.write 등)에 재설치."""
        for pg in list(self.pages):
            try:
                if not pg.is_closed():
                    self._install_frames(pg)
            except Exception:
                pass

    def actions(self) -> list[dict]:
        """요약 시퀀스: 사용자 조작(click/change/submit/key)과 네비게이션·다이얼로그만, 연속 중복 제거."""
        out, last = [], None
        for e in self.events:
            k = e.get("kind")
            if k not in ("click", "change", "submit", "key", "navigate", "dialog", "page_open"):
                continue
            if k == "navigate" and not e.get("main") and (e.get("url") or "").startswith("about:"):
                continue
            t = e.get("target") or {}
            row = {"seq": e["seq"], "kind": k, "page": e.get("page"), "frame": e.get("frame")}
            if t:
                row.update({"selector": t.get("selector"), "tag": t.get("tag"), "type": t.get("type"),
                            "label": t.get("label"), "text": t.get("text")})
                for opt in ("checked", "selected_index", "selected_text", "value_len", "value", "href", "onclick"):
                    if t.get(opt) is not None:
                        row[opt] = t[opt]
            if e.get("key"):
                row["key"] = e["key"]
            if k in ("navigate", "page_open"):
                row["url"] = e.get("url")
            if k == "dialog":
                row["message"] = e.get("message")
            sig = (k, row.get("selector"), row.get("url"), row.get("checked"), row.get("value_len"))
            if sig == last:
                continue
            last = sig
            out.append(row)
        return out


__all__ = ["NET_MAX", "BODY_MAX", "load_env", "emit", "close_if", "Run", "summarize_post", "NetCapture",
           "RECORDER_JS", "Recorder"]

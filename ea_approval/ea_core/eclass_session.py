"""ea_core.eclass_session — eclass(gate SSO + RealEANet 전자결재) 세션 상태 판정·진입 URL (읽기 전용).

역할 한 줄: 화면 URL·본문으로 "지금 어떤 로그인 단계인가"를 판정하고, 폼(DocumentView) 진입 URL 을 만든다.
주요 기능:
- classify_url(url, body) 순수 판정 → ok | needs_login | needs_name | needs_otp | needs_device_auth | rejected | not_eclass
- page_state(page) 현재 페이지 판정(읽기만), tab_kind/tab_summary/session_hint(열린 탭 분류)
- build_document_url / build_entry_url — DocumentView 는 항상 loginbyname.aspx?ReturnUrl= 경유
  (로그인된 세션의 직접 진입은 MsgBox 로 거부됨 — references/eclass/eclass_eapproval_tour.md)
- pass_name_handshake(page, name) — RealEANet 성명 핸드셰이크. 정탐에 허용된 유일한 입력 조작.
- CHANNEL_DEFAULT_PORT / CHANNEL_ENV_PORT / resolve_port — eclass 채널 포트(명시 > ECLASS_CDP_PORT > 9333).
  채널 attach 자체는 web_core.cdp_channel(공용 계층).
gate 로그인·OTP·기기인증은 절대 자동 통과하지 않는다(상태만 반환 → 호출측이 wait_user 로 보고).
검색 키워드: eclass 로그인, gate SSO, loginbyname, RealEANet, 세션 상태, OTP, 기기인증, DocumentView 진입.
"""
from __future__ import annotations

from urllib.parse import quote

from web_core import cdp_channel as _ch

# eclass 채널 — SSOT 는 spec/spec_아키텍처.md ② 채널 표
CHANNEL_DEFAULT_PORT = 9333
CHANNEL_ENV_PORT = "ECLASS_CDP_PORT"


def resolve_port(explicit: int | str | None = None) -> int:
    """eclass 채널 포트: 명시값 > ECLASS_CDP_PORT > 9333."""
    return _ch.resolve_port(explicit, CHANNEL_ENV_PORT, CHANNEL_DEFAULT_PORT)


ORIGIN = "https://eclass.krs.co.kr"
PORTAL_HOME = f"{ORIGIN}/eClassVer4/Home/Index"
LOGIN_URL = f"{ORIGIN}/eClassVer4/Account/Login"
EAPPROVAL_URL = (f"{ORIGIN}/eClassVer4/Common/Default?title=e-Approval"
                 "&menu=%2FRealEANet%2FMain%2FMainFrameTA.aspx&menuID=MED00002&newWindow=False&PmenuID=MED00001")
MAINFRAME_URL = f"{ORIGIN}/RealEANet/Main/MainFrameTA.aspx"
DOCVIEW_URL = f"{ORIGIN}/RealEANet/Main/DocumentView.aspx"
LOGINBYNAME_URL = f"{ORIGIN}/RealEANET/loginbyname.aspx"

# 실측 셀렉터(2026-07-19 원형 실측 + 2026-09-30 재확인) — 바뀌면 여기 한 곳만
SEL = {
    "login_id": "#tbUserId",
    "login_pw": "#tbPassword",
    "login_btn": "#loginButton",
    "name_input": "#txtUserName",          # RealEANet loginbyname 성명 입력
    "name_btn": "#imgbtnLogin",
    "form_title": "#ctl00_ApplineInfoInReportKRTA1_txtDocTitle",   # 폼 본체 프레임 앵커(제목)
    "editor_body": "#dext_body",           # 본문 편집기(DEXT)
}

OK = "ok"
NEEDS_LOGIN = "needs_login"
NEEDS_NAME = "needs_name"
NEEDS_OTP = "needs_otp"
NEEDS_DEVICE_AUTH = "needs_device_auth"
REJECTED = "rejected"
NOT_ECLASS = "not_eclass"
STATES = (OK, NEEDS_LOGIN, NEEDS_NAME, NEEDS_OTP, NEEDS_DEVICE_AUTH, REJECTED, NOT_ECLASS)
WAIT_USER_STATES = (NEEDS_LOGIN, NEEDS_NAME, NEEDS_OTP, NEEDS_DEVICE_AUTH)


# ── 순수 판정 ─────────────────────────────────────────────────────────
def is_eclass(url: str) -> bool:
    u = (url or "").lower()
    return u.startswith("https://eclass.krs.co.kr") or u.startswith("http://eclass.krs.co.kr")


def classify_url(url: str, body_text: str = "") -> str:
    """URL(+본문 앞부분)로 세션 단계 판정. 자동 통과 여부는 판단하지 않는다 — 상태만."""
    u = (url or "").lower()
    if not is_eclass(u):
        if u.startswith("https://gate.krs.co.kr") or u.startswith("http://gate.krs.co.kr"):
            return NEEDS_LOGIN            # gate 는 JS 리다이렉터 — 로그인 체인의 첫 단계
        return NOT_ECLASS
    if "/account/login" in u:
        return NEEDS_LOGIN
    if "loginbyname" in u:
        return NEEDS_NAME
    if "msgbox.aspx" in u or "/errorpages/" in u:
        return REJECTED
    t = (body_text or "")[:1500]
    if any(k in u for k in ("deviceauth", "device_auth")) or any(
            k in t for k in ("기기 인증", "기기인증", "PC 인증", "PC인증")):
        return NEEDS_DEVICE_AUTH
    if any(k in u for k in ("twofa", "twofactor", "/otp")) or "OTP" in t:
        return NEEDS_OTP
    return OK


def tab_kind(url: str) -> str:
    """탭 분류: docview | eapproval | login | loginbyname | msgbox | eclass | other."""
    u = (url or "").lower()
    # 로그인 계열을 먼저 본다 — ReturnUrl 안에 DocumentView/MainFrameTA 가 인코딩돼 들어 있기 때문
    if "/account/login" in u:
        return "login"
    if "loginbyname" in u:
        return "loginbyname"
    if "msgbox.aspx" in u:
        return "msgbox"
    if "documentview.aspx" in u:
        return "docview"
    if "title=e-approval" in u or "mainframeta.aspx" in u:
        return "eapproval"
    if is_eclass(u):
        return "eclass"
    return "other"


def tab_summary(targets: list[dict]) -> list[dict]:
    """/json/list 의 page 타깃(또는 {url,title}) 목록에 kind 를 붙인다."""
    out = []
    for i, t in enumerate(targets):
        url = t.get("url") or ""
        out.append({"index": i, "kind": tab_kind(url), "url": url[:200], "title": (t.get("title") or "")[:60]})
    return out


def session_hint(tabs: list[dict]) -> str:
    """탭 목록만으로 세션 상태 힌트: needs_login | eapproval_open | eclass_open | no_eclass_tab."""
    kinds = {t.get("kind") for t in tabs}
    if "login" in kinds:
        return NEEDS_LOGIN
    if kinds & {"eapproval", "docview"}:
        return "eapproval_open"
    if kinds & {"eclass", "loginbyname", "msgbox"}:
        return "eclass_open"
    return "no_eclass_tab"


def build_document_url(form_id: str, docid: str = "", ismodify: int = 0) -> str:
    """DocumentView.aspx URL(신규 작성 = DOCID 공백·ISMODIFY 0). 결재양식함 링크와 동일한 쿼리."""
    return (f"{DOCVIEW_URL}?FORMID={form_id}&DOCID={docid}&GROUPID=0&MDTID=0&DID=0"
            f"&ISMODIFY={ismodify}&OLDDOC=&ATTYN=0&ALERTMAIL=0&DOCCNT=0&EXEMTD=RETMTD&ACTYPE=0")


def build_entry_url(form_id: str, docid: str = "", ismodify: int = 0) -> str:
    """폼 진입 URL — 항상 loginbyname?ReturnUrl=<DocumentView 경로+쿼리> 경유(진입 정책)."""
    doc_url = build_document_url(form_id, docid, ismodify)
    path_q = doc_url.split("eclass.krs.co.kr", 1)[1]
    return f"{LOGINBYNAME_URL}?ReturnUrl={quote(path_q, safe='')}"


def form_id_from_url(url: str) -> str | None:
    import re
    m = re.search(r"FORMID=([^&'\"]+)", url or "", flags=re.I)
    return m.group(1) if m else None


# ── 라이브(페이지 객체) ────────────────────────────────────────────────
def page_state(page) -> dict:
    """현재 페이지의 세션 단계(읽기만). {state, url, text}."""
    try:
        url, text = page.evaluate(
            "() => [location.href, document.body ? document.body.innerText.slice(0, 1500) : '']")
    except Exception as e:  # noqa: BLE001
        return {"state": NOT_ECLASS, "url": "", "text": "", "error": str(e)[:120]}
    return {"state": classify_url(url, text), "url": url, "text": (text or "").strip()[:300]}


def find_name_frame(page):
    """loginbyname 성명 폼(#txtUserName)이 있는 frame(없으면 None)."""
    for fr in page.frames:
        try:
            if fr.query_selector(SEL["name_input"]):
                return fr
        except Exception:
            continue
    return None


def pass_name_handshake(page, name: str, timeout_ms: int = 20000) -> bool:
    """RealEANet 성명 핸드셰이크 통과 시도(1회). 성공 = URL 에서 loginbyname 이탈."""
    if not name:
        return False
    fr = find_name_frame(page) or page
    try:
        fr.fill(SEL["name_input"], name)
        page.wait_for_timeout(300)
        try:
            with page.expect_navigation(timeout=timeout_ms, wait_until="domcontentloaded"):
                fr.click(SEL["name_btn"])
        except Exception:
            page.wait_for_timeout(2500)
    except Exception:
        return False
    return "loginbyname" not in (page_state(page).get("url") or "").lower()


__all__ = ["CHANNEL_DEFAULT_PORT", "CHANNEL_ENV_PORT", "resolve_port", "ORIGIN", "PORTAL_HOME", "LOGIN_URL", "EAPPROVAL_URL", "MAINFRAME_URL", "DOCVIEW_URL",
           "LOGINBYNAME_URL", "SEL", "OK", "NEEDS_LOGIN", "NEEDS_NAME", "NEEDS_OTP", "NEEDS_DEVICE_AUTH",
           "REJECTED", "NOT_ECLASS", "STATES", "WAIT_USER_STATES", "is_eclass", "classify_url", "tab_kind",
           "tab_summary", "session_hint", "build_document_url", "build_entry_url", "form_id_from_url",
           "page_state", "find_name_frame", "pass_name_handshake"]

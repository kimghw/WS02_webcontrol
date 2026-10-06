"""web_core.cdp_channel — CDP 채널(포트 + 전용 프로필) 생존 확인·attach 공용 엔진.

역할 한 줄: 러너와 정탐(probe)이 어느 사이트든 같은 방식으로 크롬 채널에 붙게 하는 단일 결합점.
주요 기능:
- resolve_port(explicit, env_key, default) 포트 결정: 명시 인자 > 환경변수(그룹별 키) > 그룹 기본값.
  기본값이 없으면 None — 채널은 SSO 경계마다 다르므로 범용 호출측은 임의 포트를 가정하지 않는다.
- cdp_version(/json/version 엄격 확인 — Chrome 응답·ws URL 형식까지, 127.0.0.1 고정)
- cdp_targets / page_targets(/json/list — 열린 탭 목록, playwright 없이 조회)
- connect(playwright connect_over_cdp → (browser, context)), find_pages(URL 부분일치로 탭 찾기)
브라우저를 기동·종료하지 않는다(채널 기동·종료는 set_cdp_chrome 스킬). browser.close() 를 부르면
사용자 Chrome 이 닫히므로 호출측은 절대 부르지 않는다 — with sync_playwright() 종료로 연결만 끊는다.
채널 정의(포트·프로필)의 원본은 spec/spec_아키텍처.md ② 채널 표.
검색 키워드: 크롬 채널, CDP attach, connect_over_cdp, json/version, 원격 디버깅 포트, IPv4.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.request
from typing import Any

HOST = "127.0.0.1"           # localhost 는 ::1 로 풀려 거부되는 머신이 있다 — IPv4 고정
GENERIC_ENV_PORT = "CDP_PORT"


def resolve_port(explicit: int | str | None = None, env_key: str | None = GENERIC_ENV_PORT,
                 default: int | None = None) -> int | None:
    """포트 결정: 명시값 > os.environ[env_key] > default(없으면 None)."""
    if explicit not in (None, "", 0):
        return int(explicit)
    if env_key:
        env = (os.environ.get(env_key) or "").strip()
        if env.isdigit():
            return int(env)
    return default


def endpoint(port: int) -> str:
    return f"http://{HOST}:{port}"


def force_ipv4_localhost() -> None:
    """playwright/urllib 이 'localhost' 를 IPv6 로 풀어 CDP 연결이 거부되는 것을 막는다(1회 적용)."""
    if getattr(force_ipv4_localhost, "_applied", False):
        return
    orig = socket.getaddrinfo

    def _ipv4_only(host, port, *args, **kwargs):
        if isinstance(host, str) and host.lower() in ("localhost", "::1"):
            host = HOST
        if args:
            args = (socket.AF_INET,) + tuple(args[1:])
        else:
            kwargs["family"] = socket.AF_INET
        return orig(host, port, *args, **kwargs)

    socket.getaddrinfo = _ipv4_only  # type: ignore[assignment]
    force_ipv4_localhost._applied = True  # type: ignore[attr-defined]


def _get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", None) or resp.getcode()
        if status != 200:
            return None
        return json.loads(resp.read().decode("utf-8"))


def cdp_version(port: int, timeout: float = 5.0) -> dict | None:
    """/json/version 이 Chrome 브라우저 엔드포인트일 때만 payload 반환, 아니면 None(fail-closed)."""
    try:
        payload = _get_json(f"{endpoint(port)}/json/version", timeout)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    browser = payload.get("Browser")
    ws = payload.get("webSocketDebuggerUrl")
    if not isinstance(browser, str) or not browser.startswith(("Chrome/", "Chromium/", "HeadlessChrome/")):
        return None
    if not isinstance(ws, str) or not ws.startswith("ws://"):
        return None
    return payload


def channel_info(port: int) -> dict | None:
    """채널 요약 {browser, ws, endpoint} — 응답 없으면 None."""
    ver = cdp_version(port)
    if ver is None:
        return None
    return {"browser": ver.get("Browser"), "ws": ver.get("webSocketDebuggerUrl"), "endpoint": endpoint(port)}


def cdp_targets(port: int, timeout: float = 5.0) -> list[dict]:
    """/json/list — 타깃(탭·워커·확장) 목록. 실패 시 빈 리스트."""
    try:
        payload = _get_json(f"{endpoint(port)}/json/list", timeout)
    except Exception:
        return []
    return [t for t in payload if isinstance(t, dict)] if isinstance(payload, list) else []


def page_targets(port: int, timeout: float = 5.0) -> list[dict]:
    """type == page 인 타깃만(id·url·title)."""
    return [{"id": t.get("id"), "url": t.get("url") or "", "title": t.get("title") or ""}
            for t in cdp_targets(port, timeout) if t.get("type") == "page"]


def connect(playwright, port: int, timeout_ms: int = 15000):
    """이미 떠 있는 채널에 attach. 반환 (browser, context). context 는 사용자의 기본 컨텍스트(로그인 유지)."""
    force_ipv4_localhost()
    browser = playwright.chromium.connect_over_cdp(endpoint(port), timeout=timeout_ms)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return browser, ctx


def page_url(page) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def page_title(page) -> str:
    try:
        return page.title() or ""
    except Exception:
        return ""


def find_pages(ctx, *needles: str) -> list:
    """URL 에 needles 를 모두(대소문자 무시) 포함하는 페이지 목록(열린 순서)."""
    out = []
    for pg in ctx.pages:
        u = page_url(pg).lower()
        if all(n.lower() in u for n in needles):
            out.append(pg)
    return out


__all__ = ["HOST", "GENERIC_ENV_PORT", "resolve_port", "endpoint", "force_ipv4_localhost", "cdp_version",
           "channel_info", "cdp_targets", "page_targets", "connect", "page_url", "page_title", "find_pages"]

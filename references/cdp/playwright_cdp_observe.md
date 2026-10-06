# Playwright `connect_over_cdp` 로 사용자 탭 관찰하기 — 동작·제약 (실측)

사용자가 띄운 CDP 채널 Chrome 에 붙어 **사용자가 직접 조작하는 탭을 관찰**할 때 알아야 할 Playwright/Chrome 동작.
프로젝트 내부 구현은 `web_core/probe_kit.py`(Recorder·NetCapture), 결정 이력은 `spec/spec_아키텍처.md` §2.3.

## 다이얼로그(alert/confirm/prompt)

- Playwright 는 페이지에 `dialog` 리스너가 **하나도 없으면 다이얼로그를 자동으로 dismiss** 한다. 사용자 탭에 붙어 있는 동안
  사용자가 누른 "저장하시겠습니까?" confirm 이 저절로 취소될 수 있다는 뜻이다.
- 리스너를 등록하고 accept/dismiss 를 부르지 않으면 자동 dismiss 가 일어나지 않는다. 같은 채널의 다른 CDP 클라이언트가
  응답하면 그 결과가 적용된다(2026-10-06 headless 실측: 관찰 프로세스는 no-op 리스너, 다른 클라이언트가 accept → 저장 진행).
- 실제 창(headed)에서 사용자가 네이티브 다이얼로그 버튼을 직접 누르는 경우는 아직 실측하지 않았다 — 첫 실사이트 관찰 때 확인.

## 바인딩·주입 스크립트

- `page.expose_binding(name, cb)` 는 **이미 로드된 문서의 모든 frame** 과 이후 네비게이션에 함수를 만든다(실측: 기존 탭·srcdoc iframe 모두 호출됨).
  콜백의 `source` 로 `frame`·`page` 를 받을 수 있다.
- `page.add_init_script` 는 **이후 생성되는 문서에만** 적용된다. 이미 열린 문서에는 `frame.evaluate` 로 직접 주입해야 한다.
- 주입한 이벤트 리스너는 연결을 끊어도 문서에 남는다. 같은 탭에 다시 붙으면 이전 리스너가 새 바인딩을 호출하므로, 실행마다 바뀌는
  옵션은 클로저가 아니라 `window` 전역에서 이벤트 시점에 읽어야 한다. 완전히 지우려면 탭을 새로고침한다.

## 기타

- 새로 열리는 팝업/탭은 `context.on("page")` 로 잡아 같은 관찰을 붙인다(`page.on("popup")` 은 그 페이지가 연 것만).
- `request.post_data` 에는 폼 값이 그대로 들어 있다 — 기록할 때는 키 이름만 남기는 등 마스킹한다. ASP.NET postback 은
  `__EVENTTARGET`(누른 컨트롤 UniqueID)만 봐도 어떤 동작인지 알 수 있다.
- `file:`·`data:`·`about:` 요청은 `page.on("request")` 에 잡히지 않거나 의미가 없다 — 오프라인 fixture 로는 네트워크 캡처를 검증할 수 없다.
- `browser.close()` 는 사용자 Chrome 자체를 닫는다. 관찰 종료는 `sync_playwright()` 컨텍스트 종료(연결 해제)로만 한다.

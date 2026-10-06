"""web_core — 전 그룹 공용 계층(시스템 중립): CDP 채널 attach · 화면 인벤토리 · 정탐 실행 키트.

모듈 목록(각 모듈 상단 docstring 이 역할·공개 함수 요약):
- cdp_channel     크롬 CDP 채널(포트+전용 프로필) 생존 확인·attach — 러너·정탐 공용 결합점
- page_inventory  프레임·컨트롤 인벤토리(JS) · 프레임 도우미 · fieldmap DSL v1 초안 생성(범용 골격)
- probe_kit       정탐 실행 키트 — 출력 폴더/steps.jsonl · 요청/응답 캡처 · 사용자 실연(watch) 기록 · .env 로드

규약(CLAUDE.md "공용 계층 web_core"): 특정 사이트·그룹 지식(URL·셀렉터·로그인 단계)을 두지 않는다.
그룹 core(<코드>_core)와 probes 가 이것을 import 하며, web_core 는 그룹·probes 를 import 하지 않는다.
playwright 객체는 인자로만 받는다(브라우저 기동·종료는 하지 않는다 — 채널 기동은 set_cdp_chrome 스킬).
"""

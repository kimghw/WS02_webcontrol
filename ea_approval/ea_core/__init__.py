"""ea_core — 전자결재(ea) 그룹 core 계층: eclass 세션·정탐 인벤토리 확장 등 사이트 전용 엔진.

모듈 목록(각 모듈 상단 docstring 이 역할·공개 함수 요약):
- eclass_session   eclass gate SSO / RealEANet 세션 상태 판정(읽기 전용)·DocumentView 진입 URL·채널 포트
- eclass_inventory 결재양식함 카탈로그 파싱 · 폼/툴바 프레임 판별 · fieldmap 초안 eclass 어댑터

공용 계층 web_core(채널 attach·범용 인벤토리·정탐 키트)를 import 해서 쓴다 — 프로젝트 루트가 sys.path 에 있어야 한다.
규약(CLAUDE.md): primary runner 간 import 금지 — 공용부는 여기로 내리고, 사이트 무관한 것은 web_core 로 올린다.
playwright 객체는 인자로만 받는다(브라우저 기동·종료는 하지 않는다 — 채널 기동은 set_cdp_chrome 스킬).
"""

# spec_아키텍처 — WS02_webcontrol 프로젝트 구조·이행

상시 규약은 [CLAUDE.md](../CLAUDE.md)에 있고, 이 문서는 그 규약의 **근거·결정 이력·이행 상태**의 원본이다
(원본-링크 원칙 — 같은 사실을 두 곳에 쓰지 않는다).

## ① 질의·요청 히스토리

- 2026-09-30: 프로젝트 초기화 — set_claude_md 스킬로 CLAUDE.md(상시 규약)와 spec/·references/·probes/ 골격 생성.
- 2026-09-30: "eclass 에서 사용자가 자동 form 기입을 위해 탐색하는 스킬을 CDP 로 만들어 달라"(e-Approval URL 지정).
  이어서 "CLAUDE.md 에 따라 runner 를 해당 기능 폴더에 두라 — core 인지 어디인지 모르겠다" → §2.2 배치 결정.
  "샌드박스에서 테스트" → §3 검증 기록.
- 2026-10-06: "probe_eclass 는 recon 스킬이 아니네" → 실행체는 정탐 도구지만 범위가 ① create 앞부분(정탐 + recipe 초안)이고
  eclass 전용이라 범용 정탐 스킬이 아니라고 정리. 이어서 "다른 웹사이트도 정탐 후 자동화 스크립트를 만들려고 한다",
  "웹에 입력하는 스킬을 만들려면 결국 정탐하고 스크립트/실행기를 생성해야 한다" → 권장안 승인: 공용 계층 `web_core/` 신설,
  범용 정탐 `probes/web_probe.py`(사용자 실연 캡처 watch 포함), ① create 전체를 진행하는 개발 보조 스킬 `build_webauto`(§2.3).
  러너 뼈대 자동 생성은 첫 실제 대상으로 검증한 뒤(④).

## ② 확정 사양

### 2.0 업무 그룹 구성·분리 사유

- **ea(전자결재, `ea_approval/`)** — 대상 eclass e-Approval(RealEANet). 원형 krs-web-agents 의 ea 그룹과 같은
  코드·폴더명을 쓴다(이관 시 대조가 쉽도록). 2026-09-30 현재 **정탐 단계**로 working unit 이 없어 CLAUDE.md
  업무 그룹 표에는 넣지 않는다(규약: 정탐만 진행 중인 그룹은 ④에 상태만).

### 2.1 크롬 채널(포트·프로필) 구성

| 채널 | 포트 | 프로필 | 대상 시스템(SSO 경계) |
|---|---|---|---|
| eclass | 9333 | `E:\dev\krs-web-agents\chrome_profile\KRS` (원형 프로젝트 KRS 채널과 공유 — 잠정) | eclass.krs.co.kr (gate SSO + RealEANet 성명 핸드셰이크) |

- 러너·정탐은 `ECLASS_CDP_PORT`(`.env.eclass`) > 기본 9333 순으로 포트를 resolve 한다(`ea_core/eclass_session.resolve_port` →
  `web_core/cdp_channel.resolve_port`). 범용 정탐(`web_probe`)은 기본 포트가 없다 — `--port`/`CDP_PORT` 로 이 표의 포트를 넘긴다.
  이 프로젝트 전용 채널이 필요해지면 `set_cdp_chrome add <port>` 로 만들고 이 표를 먼저 고친다.

### 2.2 디렉토리 구조 — 정탐 스킬의 배치 결정(2026-09-30)

질문: "탐색 스크립트(runner)를 어느 계층에 두나(core?)". 결정(CLAUDE.md "웹 분석·정탐은 CDP 로" 절 적용):

| 무엇 | 위치 | 근거 |
|---|---|---|
| 정탐 진입 스크립트(읽기 전용 CLI) | `probes/ea_eclass_probe.py` | 규약: 정탐 스크립트는 `probes/`, 산출은 `probes/out/`. 조립·CLI·출력만 담당 |
| 재사용 엔진(세션 판정·카탈로그·eclass 초안 절) | `ea_approval/ea_core/{eclass_session,eclass_inventory}.py` | 규약: 사이트 조작·세션·변환 helper 는 core. 뒤에 만들 러너가 같은 모듈을 import 한다. 사이트 무관 부분(채널 attach·인벤토리 JS·범용 초안)은 2026-10-06 `web_core/` 로 승격(§2.3) |
| 순수 로직 테스트 | `ea_approval/ea_core/tests/test_inventory.py` | 테스트는 소유 계층 옆 |
| 절차 문서 | `.claude/skills/probe_eclass/{SKILL.md, references/runbook.md}` | 스킬 폴더는 문서만. 정탐 유틸리티라 workflow.yaml 없음(명시적 예외) |
| 외부 시스템 지식 | `references/eclass/eclass_eapproval_tour.md` | 프레임 구조·FORMID 카탈로그·진입 정책·툴바 버튼 |
| 오프라인 검증 fixture | `probes/fixtures/eclass_form_fixture.html` | 비식별 모사 폼(커밋 가능) |
| primary runner | `ea_approval/runners/`(비어 있음) | working unit 이 확정될 때 task 와 1:1 로 생성 |

`ea_recipes/`·`ea_inputs/`·`ea_data/`·`runners/` 는 `.gitkeep` 만 있다.

### 2.3 공용 계층 `web_core/`·범용 정탐·`build_webauto`(2026-10-06)

질문: "다른 사이트도 정탐 후 자동화 스크립트를 만들려면 무엇이 범용이어야 하나". 결정:

| 무엇 | 위치 | 근거 |
|---|---|---|
| 사이트 무관 엔진 | `web_core/{cdp_channel,page_inventory,probe_kit}.py` + `web_core/tests/` | 원형의 repo 내장 공용 계층(`krs_watcher/`)과 같은 역할. 사이트 지식이 없는 것만 — 의존 방향 probes·그룹 core·runner → web_core (CLAUDE.md "공용 계층") |
| 범용 정탐 CLI | `probes/web_probe.py`(status·snapshot·watch·draft·diff) | 규약: 정탐 스크립트는 `probes/`. 기본 포트 없음(채널은 SSO 경계별 — 추측 금지) |
| 사용자 실연 캡처 | `web_probe watch` → `probe_kit.Recorder` | 규약 "사용자의 실연 조작을 캡처"의 구현. 스크립트는 관찰만(클릭·입력 없음), 입력값·POST 값은 기본 마스킹(길이·키 이름·`__EVENTTARGET` 만), `--values` 는 opt-in |
| 사이트 어댑터 | `probes/<코드>_<시스템>_probe.py` + `<코드>_core/` (견본: `ea_eclass_probe` + `ea_core`) | 로그인 단계 판정·진입 URL·카탈로그처럼 사이트 고유 처리만. 범용 골격은 web_core 를 import |
| 절차 ① create 진행 | `.claude/skills/build_webauto/{SKILL.md, references/runbook.md}` | 정탐 → 실연 → recipe → core/runner → workflow·업무 스킬 → 검증을 사이트 무관하게 안내하는 개발 보조 스킬(workflow.yaml 없음 — 명시적 예외) |
| eclass 정탐 | `probe_eclass` = build_webauto 의 eclass 어댑터 | "recon 스킬"이 아니라 eclass 전용 정탐 어댑터로 위치를 정함 |
| 오프라인 fixture | `probes/fixtures/web_form_fixture.html` | 비식별 모사 폼(입력·select·체크·iframe·confirm·fetch 저장) |

- `ea_core/cdp_channel.py` 는 제거했다(복사 금지 — `web_core.cdp_channel` 로 이동, eclass 포트 기본값은 `eclass_session`).
- 범용 초안(`page_inventory.fieldmap_draft`)의 사이트 확장점: `anchor`·`title_id`·`frame`·`open_lines`·`extra_lines`.
  eclass 는 `eclass_inventory.fieldmap_draft` 가 진입(`open:` loginbyname)·제목·DEXT5 본문·툴바 절을 붙인다.

## ③ 구현 상태

- **ea 정탐(probe_eclass)** — 2026-09-30 구현·검증 완료.
  - 실사이트(채널 9333, 읽기 전용): `forms` 43건(기안문 5·양식결재 38), `form --form-id KR_EA_Form2_Test` 11프레임·54컨트롤,
    툴바·폼 프레임 판별 성공, `fieldmap.draft.yaml`·`net.json` 생성, 연 탭 자동 닫힘.
  - 순수 로직 테스트 10건 통과(`test_inventory.py`).
  - Windows Sandbox(호스트 Python·Chrome 읽기 전용 매핑, 자격증명 없음): unittest 통과, 죽은 포트 exit 2, fixture 스냅샷·초안
    생성, 공개 로그인 페이지 스냅샷 `needs_login`, `forms`/`form` 은 `needs_login` 으로 정지(exit 3). greenlet 이
    `msvcp140.dll` 을 요구해 호스트 System32 사본을 넣어야 했다(runbook §5).
- recipe·runner: 미착수(정탐 결과를 검토해 첫 working unit 을 정한 뒤).
- **공용 계층·범용 정탐·build_webauto** — 2026-10-06 구현·오프라인 검증.
  - 순수 로직 테스트: `web_core/tests/test_page_inventory.py` 11건, `ea_core/tests/test_inventory.py` 10건(이관 후 그대로) 통과.
  - 임시 채널(예비 포트 headless Chrome, scratch 프로필 — 사용자 9333 채널 미사용): `web_probe snapshot` fixture 2프레임·7컨트롤·
    초안(text 3·select 1·checkbox_enum 1), `ea_eclass_probe snapshot` eclass fixture 3프레임·18컨트롤·초안(이관 전과 같은 prefix·앵커·
    행추가 앵커). `watch`: 별도 클라이언트가 사용자 역할(입력·선택·체크·iframe 입력·저장 confirm 수락) → click 3·key 2·change 4·
    dialog 1 기록, 기록기 연결 중에도 confirm 이 자동으로 닫히지 않음, 기본 모드에서 입력값 미기록·`--values` 에서만 기록.
    검증 중 발견해 고친 것: 입력값이 `text` 필드로 새던 마스킹 구멍, 같은 탭 반복 실행 시 이전 옵션이 남던 문제, `watch --url` 새 탭이
    다이얼로그를 자동 dismiss 하던 문제, `snapshot --url --net` 이 goto 뒤에 캡처를 붙여 첫 요청을 놓치던 문제(로컬 http 로 재검증).
  - 미검증: 실사이트 watch(실제 창에서 사용자가 네이티브 다이얼로그를 직접 누르는 경우 포함), 러너 뼈대 생성.

## ④ 미결/후속

- ea 그룹: working unit 미확정 — 첫 대상 양식(예: 구매요청서 `KR_Purchase_Order`, 연구업무품의서 `KR_EA_Research_Task`)을
  사용자가 고르면 `form --form-id` 정탐 → recipe 저작 → primary runner → workflow.yaml 순으로 진행.
- 채널 9333 은 원형 프로젝트 프로필과 공유(잠정). 전용 채널로 분리할지 결정 필요(`set_cdp_chrome add`, port_manager 등록).
- 문서번호 선채번(폼을 열기만 해도 `DOCID=HER-…` 부여, references §5) — 임시보관함에 흔적이 남는지 사용자 확인 필요.
- 인벤토리 라벨 휴리스틱이 표 셀 라벨을 못 잡는 경우(기안문 수신·참조) — 라벨 규칙 보강 또는 초안 검토 시 캡처 대조.
- 공용 계층 `web_core` 는 채널·인벤토리·정탐 키트까지 승격(2026-10-06). 크롬 채널 파일락·runlog(steps/final)·로그인 공용부는
  첫 primary runner 를 만들 때 `web_core` 에 추가한다.
- build_webauto 의 러너 뼈대 생성기(recipe·runner·workflow task·테스트 골격을 한 번에 만드는 스크립트) — 첫 실제 대상(다음 자동화
  사이트)으로 절차를 한 번 돌린 뒤 반복되는 부분만 생성기로 만든다.
- 실사이트 첫 watch 때 네이티브 다이얼로그(실제 창)를 사용자가 직접 확인할 수 있는지 확인 → build_webauto runbook §5 갱신.
- CLAUDE.md 규칙 보강 후보(2026-10-06 문서 검토 지적, 사용자 확인 필요): ① "개발 보조 스킬 예외"의 면제 범위 명시(workflow.yaml 없음·
  명령 유일본을 SKILL.md 에 둠·description 규칙 적용 여부 — 현재 probe_eclass description 은 action 이름·DSL 용어를 담고 있어 업무 스킬
  규칙으로 보면 위반) ② 구조 검증 목록에 "web_core 가 그룹·probes 를 import 하지 않음" 추가(루트 회귀 러너가 생길 때 함께).
- `.env.eclass.example`(KRS_EA_NAME·ECLASS_CDP_PORT 빈 양식)은 만들어 두었다 — 실값 `.env.eclass` 는 사용자가 작성.

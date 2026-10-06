# WS02_webcontrol — 상시 규약

레시피 아키텍처(krs-web-agents 원형)를 재사용 가능한 스킬로 다듬는 웹 자동화 프로젝트. 첫 대상은 KRS eclass 전자결재(e-Approval) 폼 자동 기입이다. 이 문서는 **상시 규약만** 담는다 — 아키텍처 상세·결정 이력·이행 계획·업무 그룹
구성/분리 사유의 원본은 [spec/spec_아키텍처.md](spec/spec_아키텍처.md)이며 여기서는 링크만 둔다.

용어: **업무 그룹** = 스킬 1개 + `workflow.yaml` + 5계층 실행 자산(아래 "웹 자동화 표준 아키텍처")으로
묶인 업무 단위 집합. 스킬 하나가 여러 working unit 을 라우팅하며,
**working unit 1개 = workflow task 1개 = primary runner 1개**다. 그룹 폴더명은
`<코드>_<대표업무>/`(예: `bt_expense/`)이고 폴더 안 계층 접두어는 2글자 그룹 코드를 유지한다
(예: `bt_expense/bt_core/`). 문서·대화에서 그룹은 2글자 코드로 지칭한다.

# 일반 원칙 (전 그룹 공통)

- **사전 작성(YAML) → 검증(dry-run) → 주입 → 저장(임시저장)** 까지만 자동화한다. 상신·제출·확정·삭제는
  사용자 요청이 있을 때만, 실행 직전에 사용자에게 명시적으로 확인한 뒤 시행한다.
- **러너는 YAML 만 소비, 판단은 에이전트**: 어떤 값을 넣을지는 사전 작성 층(에이전트)이 결정해 inputs 에
  쓰고, 러너는 셀렉터·포스트백·위젯 조작만 담당한다. 사실(날짜·금액 등)이 없으면 임의 생성하지 않고
  비워 둔 채 사용자에게 묻는다.
- **dry-run 이 기본**: 쓰기(저장)는 항상 opt-in 플래그다. 기존 레코드는 명시 플래그 없이 덮어쓰지 않는다.
- **변경은 한 곳만**: 변경 원인이 recipe·input·core·runner·외부 지식 중 어디인지 먼저 분류하고 그 계층
  한 곳만 수정한다.
- **스킬 체이닝**: 그룹 간 연계는 별도 스킬·러너 없이 앞 스킬이 뒤 스킬을 이어 호출한다.
  연계 현황은 각 주제 사양서에 둔다.

# 업무 그룹

| 그룹 | 폴더 | 스킬 | 업무·대상 시스템 | 원본 사양 |
|---|---|---|---|---|
| `<코드>` | `<코드>_<대표업무>/` | `<스킬명>` | <업무 — 대상 시스템, 크롬 채널 포트> | [spec_<주제>.md](spec/spec_<주제>.md) |

- 그룹을 추가·분리·폐기할 때 이 표를 갱신한다. 분리 사유·상세 소개의 원본은 spec_아키텍처.md.
- 정탐(recon)만 진행 중이라 working unit 이 없는 그룹은 표에 넣지 않고 spec_아키텍처.md ④에 상태를 둔다.
- 스킬 트리거 판정은 각 SKILL.md 가 담당한다.

# 업무절차 2계통

모든 작업은 두 절차 중 하나다 — **① 자동화 생명주기**(working unit·러너의 create/update/retire)와
**② 실건 실행**(사용자 데이터 → 입력 생성 → 주입/실행). ①의 산출물이 ②의 실행체다.

- **실행 주체 경계**: ①은 코드 에이전트가 진행한다. ②는 특정 코드 에이전트 없이도 다른 SDK·호출자로
  실행 가능해야 한다 — 러너는 항상 호출자 중립적인 독립 CLI 로 완결되고, 판정·러너 호출이 특정
  세션 기능에 의존하면 안 된다.

## 절차 ① 자동화 생명주기 — working unit 당 primary runner 1개

1. **create**(`build_webauto` 스킬이 진행): 대상 폼·API 를 CDP 로 정탐(아래 "웹 분석·정탐은 CDP 로")하고 사용자의 실연 조작을 캡처한다 →
   recipe(`<그룹>/<코드>_recipes/<working_unit>/`)·필요 core 기능·독립 primary runner·workflow task·
   테스트를 **한 변경 세트**로 만든다. helper 는 primary 에 넣지 않고 `<코드>_core/` 로 내린 뒤
   workflow 의 `runner.helpers` 에 등록한다.
2. **update**: 변경 원인 계층 한 곳만 수정한다. CLI·경로·게이트·종점이 바뀌면 같은 변경에서 workflow 와
   테스트를 갱신하고, 그룹 회귀 → 전체 회귀 → UI/쓰기 변화 시 사용자 감독 canary 순으로 검증한다.
3. **retire**: workflow 의 `lifecycle.status` 를 `deprecated → retired` 로 전이하고 대체 task·입력 이관
   경로를 기록한다. 라우팅·호스트에서 먼저 제외하고 참조 검색·회귀가 끝난 뒤 실행 자산을 제거한다.
   실값·이력·로그를 자동 삭제하지 않는다.

## 절차 ② 실건 실행 — 사용자 데이터 접수 → 입력 생성 → 주입/실행

1. **접수·판정(에이전트)**: 사용자가 자료(양식 YAML·캡처 등)를 주면 스킬이 어떤 task·러너를 쓸지 판단하고,
   그 러너가 읽는 `input.template.yaml` 양식대로 실값을 `<코드>_inputs/` 에 작성한다. 사용자 제공
   데이터가 이미 양식과 동일하면 가공 없이 그대로 전달한다.
2. **실행(러너)**: primary runner 가 selector 로 recipe 자산을 고르고 그룹 core 를 호출해 값을 주입한 뒤
   저장(임시저장)한다. 상신·제출은 사용자 직접(일반 원칙 — 예외는 그룹 사양서에 이중 게이트로 명시).

# 웹 자동화 표준 아키텍처 — 레시피 아키텍처 (스킬 ↔ workflow ↔ 그룹 실행 자산)

웹 자동화는 모두 이 구조로 간다. 4대 구성의 절대 규칙 — ① **recipe**(어디에 뭐가 — 사이트/폼마다)
② **inputs/data**(무슨 값 — 건마다, 코드와 분리) ③ **core**(기능 하나하나 — 방식별 엔진)
④ **runner**(건 관리 — 조립·재시도·로그). 뭐가 바뀌어도 한 곳만 손댄다.

## 그룹의 5계층 (그룹 폴더 = `<코드>_<대표업무>/`, 계층 접두어 = 2글자 코드)

| 계층 | 경로 | 담는 것 | 커밋 |
|---|---|---|---|
| recipes | `<그룹>/<코드>_recipes/<working_unit>/` | 작성양식 `input.template.yaml`(선택되는 purpose/variant 별 **유일본** — 항목마다 주석으로 출처·선택 기준·검증 규칙) · 업무 스냅샷 `context.md`(진입 경로·데이터 원천·채움 규칙·쓰기 경계) · `fieldmap`(입력 키 ↔ 셀렉터/위젯 매핑, 러너가 읽는 다리 파일) · 폼/목적 규칙. 폴더명 = workflow `task.id` | 빈 양식·규칙만 |
| core | `<그룹>/<코드>_core/` | 사이트 조작·로그인/세션·검증·계산·변환 등 재사용 helper(엔진). 기능 단위 모듈·단일 책임. primary runner 간 import 금지(형제가 필요하면 공용부를 core 로 내린다). 모듈 상단에 "모듈명 — 역할 한 줄" + 주요 기능·공개 함수 요약 docstring 필수(grep 으로 찾을 수 있게 실제 업무 용어 포함) | 코드 |
| inputs | `<그룹>/<코드>_inputs/` | `input.template.yaml` 양식대로 실값을 채운 건별 **입력만**(사용자/에이전트 작성, 러너 `--input` 대상). 러너 산출물·캐시 금지 | ✗ gitignore |
| data | `<그룹>/<코드>_data/` | 증빙·manifest·결과 JSON·스크린샷·브라우저 프로필·캐시·registry·history 등 지속/런타임 data | ✗ gitignore(공개 fixture 만 예외) |
| runners | `<그룹>/runners/` | working unit 별 독립 CLI primary runner. 업무 순서 조립만 담당(로직은 core). stdout JSON 1개, dry-run 기본, `--help` 는 오프라인 로드 가능 | 코드 |

- 테스트는 소유 계층 옆에 둔다: `<코드>_core/tests/`·`runners/tests/`. 프로젝트 루트 회귀 러너가 전부를
  순차 실행한다.
- 한 폼에 목적(purpose/variant)이 여럿이면 러너를 나누지 않고 같은 primary 가 selector(`--purpose` 등)로
  해당 `input.template.yaml` 과 recipe 자산을 고른다. 물리 폼(화면)이 다르면 DOM·저장 흐름이 비슷해도
  다른 working unit·task·primary 다.

## 스킬 폴더 — 절차 문서만

- 업무 스킬 폴더(`.claude/skills/<스킬>/`)에는 `SKILL.md` + `workflow.yaml` + `references/runbook.md` 만
  둔다. 러너·core·recipe/template·실값·런타임 data 를 스킬 폴더에 두지 않는다.
- **스킬의 책임** = 사용자 자료 판정·입력 사전 작성·workflow resolve·결과 해석 절차. SKILL.md 는 에이전트
  절차 + workflow/runbook 링크만, runbook 은 전제·입력 검증·판정 기준·에러 대응만(명령 중복 금지),
  정확한 명령·모드·게이트는 workflow.yaml 이 유일본.
- **SKILL.md frontmatter `description`**: 대상 시스템과 사용자가 이용할 수 있는 기능만 1~2문장. 내부
  경로·task/runner/core 이름·명령·모드·게이트·포트·단계별 절차·구현 상태는 넣지 않는다.
- 크롬 채널 포인터·데이터 동기화 같은 자족 유틸리티·개발 보조 스킬은 명시적 예외이며 업무 러너로
  계산하지 않는다.

## workflow.yaml = 단일 기계판독 SSOT

- 업무(task) → recipe·input·data·primary runner·helpers·정확한 기동 명령/모드·게이트·종점·생명주기 매핑의
  원본. `meta.schema_version: 2` 와 task 별
  `id·label·aliases·nav·recipe(context/template)·input(root/arguments)·data(root/screenshots/…)·
  runner(primary/command/modes/helpers)·gates·end_point·lifecycle(status/introduced_at/replaces/replaced_by/retired_at)`
  를 둔다. `runner.command` 는 `python <primary>`, `modes.<이름>.args` 는 list, `writes` 로 부작용 단계
  (`false`·`draft`·`submit` 등)를 표시한다.
- `gates`: `validate`(저장 전 의미 검증)·`channel_lock`(크롬 채널 파일락 대상 모드)·`draft_save`(저장 정책
  manual/auto·조건)·`forbidden`(러너가 절대 수행하지 않는 동작 — 상신·제출·삭제 등).
- `lifecycle.status` 는 `active|deprecated|retired`, **active 만 라우팅·실행**된다.
- SKILL.md·runbook·template 은 이 값을 중복하지 않고 링크한다(template 은 `gate_ref` 로 역참조).
  **불일치 시 workflow 가 우선**한다. 호출자(스킬 호스트 등)는 자체 러너 매핑을 두지 않고 workflow 를
  resolve 한다.

## primary 와 helper 경계

- 독립 라우팅·실행되는 업무만 primary 다. 로그인·intake·계산·변환·검증처럼 primary 가 호출하거나 전후
  단계에서 쓰는 실행체는 core 로 내리고 `runner.helpers[]` 에 `id·path·role·invocation` 을 등록한다.
- primary CLI 가 얇은 wrapper 라면 조립 engine 을 core 에 둘 수 있지만 그 engine 도 helper 로 명시하고
  독립 사용자 진입점으로 노출하지 않는다. helper 가 독립 사용자 업무가 되면 새 task/primary 로 승격한다.

## 공용 계층 `web_core/` — 사이트 무관 엔진

- 프로젝트 루트 `web_core/` 에는 특정 사이트·그룹 지식(URL·셀렉터·로그인 단계)이 없는 엔진만 둔다 — CDP 채널 attach,
  범용 화면 인벤토리·fieldmap 초안, 정탐 키트(실행 골격·요청/응답 캡처·사용자 실연 기록). 테스트는 `web_core/tests/`.
- 의존 방향은 probes·그룹 core·runner → `web_core` 한쪽뿐이다. `web_core` 는 그룹·probes 를 import 하지 않는다.
  그룹 core 의 기능이 다른 사이트에서도 필요해지면 사이트 지식을 떼어 `web_core` 로 올린다(복사 금지).

## 구조 검증 (회귀에서 fail-closed)

모든 workflow 포인터·명령 경로가 실재하고, 모든 primary runner 가 정확히 한 task 에 등록되며(전역 유일),
helper 가 core 와 workflow 양쪽에 등록되고, 업무 스킬 폴더에 실행 자산이 없고, inputs/data 가 물리
분리·gitignore 됐는지를 회귀에서 검사한다. 공유 코드는 계약된 계층 자산을 import 만 하고 복사하지 않으며,
역방향·순환 import 를 금지한다.

# 웹 분석·정탐은 CDP 로

웹의 페이지 구조와 요청/응답 구조 분석은 **CDP(Chrome DevTools Protocol)** 로 한다. 화면을 눈으로 보고
추측한 셀렉터·엔드포인트를 recipe 에 쓰지 않는다.

- **채널 = 포트 + 프로필**: 크롬을 `--remote-debugging-port=<포트>` + 전용 `--user-data-dir` 로 기동하고,
  자동화(러너)와 분석(정탐)이 같은 채널에 붙는다(Playwright `connect_over_cdp` 등). 생존 확인은
  `http://127.0.0.1:<포트>/json/version`. SSO 경계(도메인 묶음)마다 채널을 나누고 개인 브라우징
  프로필과 섞지 않는다. 채널 정의(포트·프로필 경로)는 한 곳(바인딩 SSOT)에 두고 러너는 그것을 resolve 한다.
- **분석 대상 ↔ CDP 도메인**:
  - 페이지 구조 — 프레임/iframe 트리, 컨트롤 id·name·type, 라벨, 그리드/팝업, postback 위젯 →
    `DOM`·`Runtime.evaluate`(필드 인벤토리 JSON 으로 저장).
  - 요청/응답 구조 — 엔드포인트·메서드·헤더·쿠키/세션 토큰·페이로드·응답 스키마·XHR/fetch 순서 →
    `Network`(request/response 이벤트, 응답 본문 캡처). 조회가 세션쿠키 기반 REST 로 재현되면 UI 조작
    대신 API 호출을 선택지로 검토한다(쓰기 API 는 UI 와 같은 게이트).
  - 화면 전이·다이얼로그·다운로드 → `Page`; 콘솔·JS 오류 → `Log`·`Runtime`.
- **정탐(recon) 스크립트는 `probes/`**: 읽기 전용(저장·제출·삭제 클릭 금지, 로그인 핸드셰이크만 허용),
  산출은 `probes/out/`(gitignore). 사용자의 실연 조작을 캡처할 때는 사용자 감독 하에 진행한다.
  일회성 탐사 변형도 `probes/` 에만 만든다. 사이트 무관 범용 정탐은 `probes/web_probe.py`(실연 캡처 `watch` 포함),
  사이트 고유 세션·진입 처리가 필요하면 어댑터 `probes/<코드>_<시스템>_probe.py`(사이트 고유 엔진은 그룹 core, 범용은 `web_core`)를 둔다.
- **정탐 결과의 귀속**: 폼 구조·셀렉터·입력 항목 → 그 working unit 의 recipe(`fieldmap`·`context.md`·
  `input.template.yaml`), 외부 시스템의 동작 방식·제약(API 스펙·세션 규칙·한도) → `references/`,
  결정·구현 상태 → 해당 `spec/spec_<주제>.md` ②③. fieldmap 은 손수정하지 않고 probe 로 검증한 뒤 반영한다.

# 보안 기본값 (실값은 개인정보 상시 혼재)

- 모든 `<그룹>/<코드>_inputs/`·`<그룹>/<코드>_data/`·`logs/`·`probes/out/`·크롬 프로필·캡처(`*.png`)는
  **기본 gitignore**. 커밋은 빈 recipe/template·비식별 fixture·코드·문서만.
- 자격증명은 프로젝트 루트 `.env.*`(gitignore, 빈 양식 `.env.*.example` 만 커밋)가 SSOT — 러너가 세션 호출
  전 주입하며 스킬 폴더·명령행·문서에 비밀을 두지 않는다.
- 로그·캡처에 실명·금액이 남으므로 외부 공유 전 마스킹한다.

# 로그·감독 계약 (요약)

- 러너는 1스텝 1행의 실행 로그(`logs/<러너>/<일시_키>/steps.jsonl`, 성공/실패 무관 상시)와 종료 판정
  (`final.json`, 원자적 finalize)을 남긴다. verdict = `ok|retry|fail|wait_user`(OTP·기기인증 등은
  wait_user — 자동 통과 금지).
- 크롬 채널은 OS 파일락으로 상호배제한다(문서 트랜잭션 전체 범위).
- 판정은 결정론 판정기(에러 카탈로그) 1차, LLM 은 해석·에스컬레이션 2차. 미등록 에러 = 중단.
- 상세 필드·락 키·재개 규칙의 원본은 spec_아키텍처.md, 그룹별 적용 상태는 각 그룹 사양서 ③④.

# 지식저장소 <cwd>/references — 모듈과 무관한 재사용 지식

- 대상: 외부 시스템의 동작 방식·제약(API 스펙, 스크래핑 방법, 한도 등). 프로젝트 내부 구현
  이력은 사양서에 두고 여기 중복하지 않는다.
- 갱신 트리거: 외부 시스템에 대해 새로 알아낸 사실이 있으면 **답변 완료 시점**에 반영한다.
  관련 파일이 이미 있으면 그 파일에 추가한다.
- 사용자 요청 시 관련 자료가 있는지 우선적으로 참조한다.

# 문서 갱신 검토 (서브에이전트)

- 판별 기준은 분량이 아니라 **의미**: 확정 사양·확정 사실이 새로 생기거나 바뀌면 한 줄이어도
  서브에이전트로 일관성·논리성을 검토하고, 이력 추가(①)·상태 갱신(③)·오타 수정은 문서가
  새것이어도 생략한다.

# 요구사항·질의 관리 — <cwd>/spec 의 "주제별 사양서 하나"로 통합

- 질의·요청의 히스토리와 그것을 정리한 사양은 **주제/기능별 사양서 1개**(`spec_<주제>.md`)로
  합쳐 관리한다.
- 사양서 구조: ① 질의·요청 히스토리(날짜·원문 요지) ② 확정 사양 ③ 구현 상태 ④ 미결/후속.
- 작성 주체: 사용자 또는 코드 에이전트. 비자명한 구현은 착수 전에 ②를 먼저 만들고, 구현 후 ③을 갱신한다.
- 조회성 질문의 답도 해당 주제 사양서 ①에 한 줄로 남긴다. 단:
  - 답이 외부 시스템 지식뿐이면 원본은 references 에 두고, 관련 사양서가 **이미 있을 때만** ①에 한 줄+링크.
  - 프로젝트와 무관한 일회성 조회는 사양서를 새로 만들지 않는다.
- 원본-링크 원칙: 같은 사실은 한 문서가 원본, 다른 문서는 링크만. 진행 상태는 그 주제 사양서 ③에만 기록.
- 구형 사양서(①~④ 절 없는 것)는 일괄 개편하지 않는다 — 그 주제를 다시 다룰 때 ①~④ 절을
  추가하고 기존 본문은 ②로 간주해 점진 이관한다.

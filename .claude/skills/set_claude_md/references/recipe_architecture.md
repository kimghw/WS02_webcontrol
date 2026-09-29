# 레시피 아키텍처 — 상세 설명과 실례

CLAUDE.md 템플릿(`../assets/CLAUDE.template.md`)에는 상시 규약만 압축해 넣었다. 이 문서는 그 규약이
실제 프로젝트에서 어떤 모양으로 나타나는지를 보여 주는 참고 자료다. 원형은 `E:\dev\krs-web-agents`
(KRS 업무 자동화 — eclass 전자결재·출장비·근태·일일보고·rERP·IRIS·회의실 등 9개 업무 그룹).
새 프로젝트에서 "이 절을 왜 이렇게 쓰나"가 궁금할 때, 또는 첫 업무 그룹을 스캐폴딩할 때 읽는다.

## 1. 왜 이 구조인가 — 4대 구성의 절대 규칙

사용자가 확정한 규칙(2026-07-18): 웹 자동화 1건은 네 가지 관심사로 나뉘고, **무엇이 바뀌어도 한 곳만
손댄다**.

| 구성 | 질문 | 바뀌는 계기 | 물리 위치 |
|---|---|---|---|
| recipe | 어디에 뭐가 있나 (사이트/폼마다) | 사이트 개편, 필드 추가 | `<코드>_recipes/<working_unit>/` |
| inputs / data | 무슨 값을 넣나 (건마다) | 건별 실값, 산출물 | `<코드>_inputs/` · `<코드>_data/` |
| core (engine) | 기능 하나하나 어떻게 하나 (방식별) | 위젯 조작법·로그인 방식 변경 | `<코드>_core/` |
| runner | 건 하나를 어떻게 관리하나 (조립·재시도·로그) | 업무 순서·게이트 변경 | `runners/` |

이렇게 나누면 사이트가 개편돼도 recipe 의 fieldmap 만 고치고, 새 건을 처리할 때는 inputs 만 새로 쓰며,
러너 코드는 손대지 않는다. 러너 하나가 모든 걸 품고 있으면 그 반대가 된다.

## 2. 실례 — 업무 그룹 하나의 실물 (dr 일일 업무보고)

```
dr_dailyreport/                         ← 그룹 폴더 <코드>_<대표업무>
├── dr_recipes/dailyreport/             ← recipe. 폴더명 = workflow task.id
│   ├── context.md                      ← 업무 스냅샷: 업무와 종점 / 진입과 데이터 원천 / 채움 규칙 / 검증과 쓰기 경계
│   ├── input.template.yaml             ← 작성양식(빈 양식·주석으로 선택지·기준). 실값 금지
│   ├── participation.template.yaml     ← 보조 양식
│   └── work_ledger.template.yaml
├── dr_core/
│   ├── dr_balance.py                   ← helper(순수 계산). 상단 docstring: "모듈명 — 역할 한 줄" + 서브커맨드 요약
│   └── tests/test_balance.py
├── dr_inputs/                          ← gitignore. 양식대로 채운 실값만
│   ├── dr_input.yaml
│   ├── participation.yaml
│   └── work_ledger.yaml
├── dr_data/                            ← gitignore. 러너 산출물
│   ├── dr_list.json · dr_results.json
│   └── screenshots/
└── runners/
    ├── dr_report_run.py                ← primary runner(독립 CLI, stdout JSON 1개, dry-run 기본)
    └── tests/

.claude/skills/dr-dailyreport/          ← 스킬 폴더: 절차 문서만
├── SKILL.md                            ← 에이전트 절차 + workflow/runbook 링크
├── workflow.yaml                       ← 기계판독 SSOT
└── references/runbook.md               ← 전제·입력 검증·판정 기준·에러 대응(명령 중복 금지)
```

EA(전자결재)처럼 한 working unit 이 물리 폼 1개 + 목적 여럿을 가지면 recipe 가 한 층 깊어진다:
`ea_recipes/<working_unit>/forms/<form>/{manifest.yaml, fieldmap.yaml, purposes/<purpose>/{purpose.yaml,
input.template.yaml, body_spec.yaml, attach_rules.yaml, context.md}}`. 같은 `form_id` 는 같은 primary 가
`--purpose` 로 고르고, `form_id` 가 다르면 working unit·task·primary 를 새로 만든다.

## 3. recipe 파일들이 각각 담는 것

- **input.template.yaml** — 러너가 읽는 입력의 빈 양식이자 스키마. 항목마다 주석으로 (a) 어느 화면
  컨트롤에 들어가는지 (b) 선택형이면 선택지와 선택 기준 (c) 사실값이면 "없으면 질문, 임의 생성 금지".
  맨 위에 `gate_ref: ".claude/skills/<스킬>/workflow.yaml#tasks.<id>.gates"` 로 게이트를 역참조하고
  자체 save_gate 를 두지 않는다. purpose/variant 별로 **완결형 유일본**(공통 조각 합성 방식 금지).
- **context.md** — 에이전트가 값을 채울 때 읽는 업무 스냅샷. 고정 절: 업무와 종점 / 진입과 데이터 원천 /
  recipe 와 채움 규칙 / 검증과 쓰기 경계. 경로는 repo 루트 기준. 정책 원본(spec)을 링크만 한다.
- **fieldmap.yaml** — 입력 키 ↔ 셀렉터/위젯 primitive 매핑(text·select·checkbox_enum·date·repeat_row·
  frame_reacquire·postcondition 등). 러너가 읽는 "다리 파일"이므로 **손수정 금지 — probe 로 실측한
  인벤토리에서만 갱신**. 출처(어느 probe 산출물, 실측일)를 헤더 주석에 남긴다.
- **manifest.yaml** — working_unit_id·label·ui_mode(form/body)·form_id·hooks 여부.

## 4. workflow.yaml 뼈대

```yaml
meta:
  schema_version: 2            # 2 고정 — 아니면 호출자가 거부
  family: dr                   # 그룹 2글자 코드
  skill: dr-dailyreport
  system: <대상 시스템·URL>

tasks:
  - id: dailyreport            # = recipe 폴더명
    label: 일일 업무보고 작성·제출
    aliases: [일일보고, 업무일지]
    nav: {domain: https://…, entry: 메뉴 → 프레임 → 화면}
    recipe:
      context:  dr_dailyreport/dr_recipes/dailyreport/context.md
      template: dr_dailyreport/dr_recipes/dailyreport/input.template.yaml
    input:  {root: dr_dailyreport/dr_inputs, work_file: …/dr_input.yaml, format: yaml, arguments: [--input]}
    data:   {root: dr_dailyreport/dr_data, screenshots: dr_dailyreport/dr_data/screenshots, logs: …}
    runner:
      primary: dr_dailyreport/runners/dr_report_run.py      # 전역 유일, task 와 1:1
      command: python dr_dailyreport/runners/dr_report_run.py
      modes:
        list:       {args: [--list, --from, "{from}", --to, "{to}"], writes: false}
        write-dry:  {args: [--write, --input, "{input}"],            writes: false}
        write-save: {args: [--write, --input, "{input}", --save],    writes: draft}
        submit:     {args: [--submit, --date, "{date}", --confirm],  writes: submit}
      helpers:
        - {id: balance, path: dr_dailyreport/dr_core/dr_balance.py, role: "…", invocation: cli}
    gates:
      submit_double_gate: {required_for: [submit], gates: [사용자 확인, --confirm]}
      channel_lock: {required_for: [list, write-dry, write-save, submit], channel: krs}
      forbidden: [삭제, 확정]
    end_point: 조회·검토·"작성중" 저장까지. 이중 게이트 통과 건만 제출. 삭제·확정은 사용자 직접.
    lifecycle: {status: active, introduced_at: 2026-07-20, replaces: [], replaced_by: null, retired_at: null}
```

`modes.*.writes` 는 호출자가 "이 모드가 무엇을 바꾸는가"를 기계적으로 판단하는 근거다(`false` 는
읽기 전용, `draft` 는 임시저장, `submit` 은 제출). dry 모드에 쓰기가 있으면 호출자가 거부한다.

## 5. CDP 정탐(probe) 패턴

```
probes/
├── <코드>_<대상>_probe.py     ← 읽기 전용. docstring 에 "확인 대상 1) 2) 3)" 과 "⚠ 읽기 전용 — 저장 클릭 없음" 명시
└── out/                       ← gitignore. inventory.json · shot.png · <대상>.json
```

전형적인 흐름:

1. 채널 생존 확인 — `GET http://127.0.0.1:<포트>/json/version`. 죽어 있으면 전용 프로필로 크롬 기동
   (`--remote-debugging-port=<포트> --user-data-dir=<프로필> --remote-debugging-address=127.0.0.1`).
   `localhost` 가 `::1` 로 풀려 실패하는 머신이 있으므로 `127.0.0.1` 을 쓴다.
2. `playwright.chromium.connect_over_cdp("http://127.0.0.1:<포트>")` → 기존 context/page 재사용
   (로그인 세션 유지).
3. **페이지 구조**: `page.evaluate(JS)` 로 프레임별 컨트롤 인벤토리(id·name·type·label·options·disabled) 를
   JSON 으로 뽑는다. 팝업·postback 은 상태 스냅샷을 전/후로 찍어 비교한다.
4. **요청/응답**: `page.on("request")`·`page.on("response")` 또는 `context.request` 로 XHR/REST 를 캡처해
   엔드포인트·메서드·헤더·페이로드·응답 스키마를 기록한다. 조회가 세션쿠키만으로 REST 재현되면
   그 사실을 references 에 남기고 UI 조작 대신 API 호출을 검토한다.
5. 산출은 `probes/out/` 에, 확정 사실은 recipe(fieldmap·context) 와 `references/<시스템>/` 에 반영한다.

## 6. .gitignore 패턴

그룹마다 `inputs/*`·`data/*` 를 통째로 무시하고 `.gitkeep` 과 공개 fixture 폴더만 예외로 연다.

```
<그룹>/<코드>_inputs/*
!<그룹>/<코드>_inputs/.gitkeep
<그룹>/<코드>_data/*
!<그룹>/<코드>_data/.gitkeep
!<그룹>/<코드>_data/screenshots/
<그룹>/<코드>_data/screenshots/*
!<그룹>/<코드>_data/screenshots/.gitkeep
logs/  probes/out/  *.png  chrome_profile/  .env*  !.env*.example
```

set_claude_md 의 `scaffold` 는 그룹 무관 와일드카드(`*_inputs/*`, `*_data/*`)를 넣는다. 그룹이 생기면
위처럼 그룹별 예외를 추가한다.

## 7. 공용 계층 (그룹 밖)

| 위치 | 담는 것 |
|---|---|
| `references/` | 외부 시스템 지식(API 스펙·세션 진입 규칙·한도·화면 투어). 시스템별 하위 폴더 |
| `spec/spec_<주제>.md` | ①질의 이력 ②확정 사양 ③구현 상태 ④미결. `spec_아키텍처.md` 가 구조·이행의 원본 |
| `probes/` | 정탐 스크립트(읽기 전용) + `out/` |
| `<공용 워커 패키지>/` | 크롬 채널 바인딩·기동, 공통 로그인, 실행 로그(runlog) 등 전 그룹 공용 — 러너는 단일 결합점 모듈을 경유해 import |
| `run_regress.py` | 전 그룹 테스트 순차 실행 + 구조 계약 테스트(workflow 포인터 실재·primary 유일·스킬 폴더 순수성·inputs/data 분리) |
| `.env.<시스템>` / `.env.<시스템>.example` | 자격증명 SSOT(gitignore) / 빈 양식(커밋) |

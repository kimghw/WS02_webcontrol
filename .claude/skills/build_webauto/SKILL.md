---
name: build_webauto
description: 새 웹사이트·웹 폼의 자동 입력(자동 기입·임시저장) 기능을 만든다 — CDP 크롬 채널로 화면 구조·요청/응답을 읽기 전용 정탐하고, 사용자가 직접 입력·저장하는 실연을 기록해, 그 결과로 작성양식·필드맵·실행기(러너)·업무 스킬을 만든다. "이 사이트/이 화면 자동 입력 만들어", "웹 폼 자동화 스크립트 만들어", "정탐해서 러너 만들어", "새 업무 자동화 추가", 기존 자동화의 화면 변경 재정탐 요청 시 사용. 이미 만든 자동화로 실건을 넣는 일(각 업무 스킬), 상신·제출·삭제 실행에는 쓰지 않는다.
argument-hint: "[<대상 URL 또는 사이트/업무 설명> | status | snapshot | watch | draft | diff | help] [--port N]"
---

# build_webauto — 웹 자동 입력 만들기(절차 ① create)

웹에 무언가를 자동으로 입력하는 업무 스킬은 늘 **정탐 → 실연 캡처 → recipe → core/runner → workflow·업무 스킬 → 검증**
순서로 만든다. 이 스킬은 CLAUDE.md "절차 ① 자동화 생명주기 — create" 를 사이트와 무관하게 진행하는 개발 보조 스킬이다
(업무 러너가 아니므로 workflow.yaml 이 없다 — CLAUDE.md 명시적 예외). 만들어진 업무 스킬이 절차 ② 실건 실행을 맡는다.

> 배치: 이 폴더에는 절차 문서만 있다. 범용 정탐 CLI 는 `probes/web_probe.py`(읽기 전용, stdout JSON 1개), 엔진은 공용 계층
> `web_core/`(cdp_channel·page_inventory·probe_kit). 사이트 전용 정탐 어댑터가 있으면 그것을 쓴다(예: eclass → `probe_eclass`).

```
python "<프로젝트 루트>/probes/web_probe.py" <action> --port <채널 포트> [옵션]
```

| action | 동작 | 부작용 |
|---|---|---|
| `status` | 채널 생존(`/json/version`) + 열린 탭 목록. playwright 불필요 | 없음 |
| `snapshot [--tab S \| --url U]` | 대상 탭(기본: 마지막 일반 탭)의 프레임/컨트롤 인벤토리 + 전체 캡처 + fieldmap 초안. `--net` 이면 요청/응답 요약(`--url`: 첫 요청부터, 기존 탭: `--net-seconds` 동안) | `--url` 이면 새 탭 열기·닫기(`--keep` 유지). 기존 탭은 읽기만 |
| `watch [--tab S \| --url U] [--seconds N]` | **사용자 실연 캡처** — 사용자가 직접 조작하는 동안 클릭·변경·제출·Enter/Tab, 팝업·네비게이션·다이얼로그, 요청/응답(POST 키·postback 대상)을 기록. 시작/끝 인벤토리 + diff | 스크립트는 클릭·입력 없음(관찰만 — 다이얼로그도 응답하지 않아 사용자가 직접 누른다). 출력 폴더에 `STOP` 파일을 만들면 즉시 종료 |
| `draft --inventory F [--anchor SEL]` | inventory.json → `fieldmap.draft.yaml` (오프라인) | 파일 1개 |
| `diff --before F --after F` | 조작 전/후 인벤토리 비교(늘어난/사라진 컨트롤) (오프라인) | 없음(`--out` 시 파일) |
| `help` | action·옵션 표 | 없음 |

옵션: `--port N`(또는 `CDP_PORT` — 기본값 없음, 채널은 추측하지 않는다) · `--env FILE` · `--out DIR|FILE` · `--name KEY` ·
`--keep` · `--wait-ready SEL` + `--wait-user SEC`(기본 60 — 로그인 등 사용자 조치 대기) · `--net` · `--net-seconds S`(기본 5) ·
`--bodies`(xhr/fetch 응답 본문) · `--values`(입력값·POST 원문 기록 — 기본은 마스킹) · `--seconds N`(watch, 기본 180) ·
`--no-inventory`(watch) · `--anchor SEL`(초안 frame_reacquire 앵커 — snapshot·watch·draft) · `--form-id ID`(초안 form_id 표기 — draft).

## 인자

| 인자 | 동작 |
|---|---|
| `help` / `-h` / `--help` | 이 인자 표와 action 표만 출력하고 종료 |
| (없음) 또는 대상 설명/URL | 아래 **절차** 를 처음부터 진행(대상 확정부터) |
| `status` / `snapshot` / `watch` / `draft` / `diff` | 해당 action 만 실행하고 보고 형식으로 결과만 |

## 절차

1. **대상 확정** — 사이트(origin)·업무·화면을 확정하고 그룹을 정한다: 기존 그룹이면 그 `<코드>_<대표업무>/`, 새 그룹이면
   2글자 코드·폴더명을 사용자와 정한다(CLAUDE.md 용어). working unit 이름(= 나중의 workflow `task.id`)을 가안으로 정한다.
   물리 화면이 다르면 다른 working unit 이다.
2. **채널** — `spec/spec_아키텍처.md` ② 채널 표에서 그 사이트의 SSO 경계에 맞는 포트를 고른다. 없으면 `set_cdp_chrome add <port>`
   로 채널을 만들고(`port_manager` 로 포트 등록) 표에 먼저 행을 추가한다. 그다음 `status`. `stopped` 면 사용자가 아이콘으로 띄우게 하고 멈춘다.
3. **정탐 도구 선택** — 사이트 어댑터(`probes/<코드>_<시스템>_probe.py` + 해당 스킬, 예: eclass → `probe_eclass`)가 있으면 그것으로
   세션 판정·진입을 처리하고, 없으면 `web_probe` 를 쓴다. 로그인·OTP·기기인증은 사용자가 브라우저에서 직접 한다.
4. **화면 정탐** — 사용자가 대상 화면(빈 입력 폼)까지 이동한 뒤 `snapshot --tab <부분문자열> --net`. 결과 판정은
   [runbook §2](references/runbook.md). 목록/조회 화면이면 `--bodies` 로 응답 스키마를 보고 REST 재현 가능성을 검토한다.
5. **실연 캡처** — 사용자에게 "지금부터 N초 동안 평소처럼 입력하고, 가능하면 **임시저장까지** 눌러 달라(상신·제출은 누르지 말 것)" 고
   안내한 뒤 `watch --tab <부분문자열> --seconds N`. 테스트 값·테스트 문서를 권한다. 사용자가 끝났다고 하면 출력 폴더에 `STOP` 파일을
   만들어 끝낸다. 행추가·팝업 선택·첨부처럼 단계가 많은 조작은 단계별로 나눠 여러 번 캡처한다.
6. **분석·귀속** — 확정 사실만 옮긴다([runbook §3](references/runbook.md) 체크리스트):
   - `actions.json`(조작 순서·위젯 처리·다이얼로그) + `fieldmap.draft.yaml` + `diff.json`(동적 컨트롤) →
     recipe `<그룹>/<코드>_recipes/<unit>/`: `fieldmap.yaml`(초안을 복사해 `source:` 를 채우고 헤더에 출처 inventory·실측일),
     `input.template.yaml`(항목마다 출처·선택 기준·검증 규칙 주석), `context.md`(진입 경로·데이터 원천·채움 규칙·쓰기 경계).
   - `net.json`(저장 엔드포인트·postback 대상 `__EVENTTARGET`·응답) → `context.md` 의 저장 흐름, 외부 시스템 동작·제약 →
     `references/<시스템>/`, 결정·상태 → 그 주제 `spec/spec_<주제>.md` ②③.
   - 같은 사이트에서 반복될 지식(세션 판정·진입 URL·고유 위젯)은 그룹 core 로, 사이트와 무관한 것은 `web_core` 로 올린다.
7. **실행기** — `<그룹>/<코드>_core/` 에 필요한 helper(로그인·입력 primitive·검증)를 기능 단위로 만들고, primary runner
   `<그룹>/runners/<unit>.py` 를 [runbook §4 러너 계약](references/runbook.md)대로 만든다(dry-run 기본, 저장은 opt-in 플래그,
   stdout JSON 1개, `--help` 오프라인, 로그 `logs/<러너>/…`). 러너는 fieldmap·input 만 읽는다 — 셀렉터를 코드에 박지 않는다.
8. **workflow·업무 스킬** — 그룹 업무 스킬 `.claude/skills/<스킬>/`(`SKILL.md` + `workflow.yaml` + `references/runbook.md` 만)에
   task 를 등록한다(gates.forbidden 에 상신·제출·삭제). CLAUDE.md 업무 그룹 표에 행을 추가한다(정탐만 끝난 상태면 spec ④ 에만).
9. **검증** — core/runner 테스트 → 러너 `--help`·dry-run → 사용자 감독 canary(임시저장 1건, 결과 화면 캡처로 대조) → 구조 검증.
   UI/쓰기 변화가 있는 update 도 같은 순서.
10. **보고** — 아래 형식. 남은 결정(예: 첨부·본문 편집기 처리)은 spec ④ 에 남긴다.

## 보고 형식

```
대상: <사이트/화면>  그룹: <코드> (<신규|기존>)  unit: <working_unit>
채널 <port>: listening | stopped   정탐 도구: web_probe | <어댑터>
정탐: 프레임 M · 컨트롤 K · 초안 text n · select n · checkbox_enum n · repeat_row n · hooks n
실연: 조작 N건 · 팝업 P · 다이얼로그 D · POST R건(저장 후보: <url/__EVENTTARGET>) · diff +a/-r
산출: probes/out/<run>/…   귀속: recipe ✓/✗ · references ✓/✗ · spec ✓/✗
다음: <채널 기동 | 사용자 실연 | recipe 저작 | runner 작성 | canary>
```

한 줄씩만. JSON 을 그대로 되풀이하지 않는다. 열어 둔 탭이 있으면(`--keep`) 적는다.

## 판단 규칙

- **정탐 스크립트는 읽기 전용이다.** `snapshot`/`watch` 는 어떤 클릭·입력도 하지 않는다. 저장·제출을 눌러 보는 것은 사용자
  실연에서 사용자가 판단해 직접 할 뿐이고, 상신·제출·확정·삭제는 실연에서도 권하지 않는다.
- **값은 기본 마스킹.** `watch` 는 입력값 대신 길이만, POST 는 키 이름과 `__EVENTTARGET/__EVENTARGUMENT` 만 남긴다. 값의 형식(날짜
  포맷·코드값)을 알아야 할 때만 사용자 동의 후 `--values` 를 쓰고 테스트 값으로 시연하게 한다. 클릭한 셀·목록 항목의 표시 텍스트는
  마스킹하지 않는다(어느 항목을 골랐는지 알아야 하므로) — 산출물은 전부 `probes/out/`(gitignore).
- **초안은 정본이 아니다.** `fieldmap.draft.yaml` 은 휴리스틱(라벨·접두·행 패턴)이다. 캡처(`shot.png`)와 실연 기록으로 대조하고
  canary 로 검증한 뒤에만 recipe 로 승격한다. fieldmap 은 손으로 지어내지 않는다.
- **API 대안.** 실연의 `net.json` 에서 저장·조회가 세션 쿠키 기반 REST/postback 으로 재현되면 UI 조작 대신 API 호출을 선택지로
  제시한다(쓰기 API 도 UI 와 같은 게이트).
- **한 변경 세트.** create 는 recipe·core·primary runner·workflow task·테스트를 한 번에 만든다. 일부만 만들고 멈출 때는 spec ③ 에
  어디까지 했는지 적는다.
- **사이트 어댑터 승격.** 같은 사이트를 두 번 이상 정탐하며 로그인 단계 판정·진입 URL 규칙이 필요해지면
  `probes/<코드>_<시스템>_probe.py`(조립만) + `<코드>_core/` 모듈로 어댑터를 만든다(probe_eclass 가 견본).

## JSON 필드

공통: `ok`, `action`, `port`, `state`, `hint`, `out`, `files{}`, 오류 시 `error`.
exit 0 성공 / 1 오류(포트 미지정 포함) / 2 채널·대상 없음 / 3 wait_user(`--wait-ready` 미등장) / 6 수집 0건(`PROBE_EMPTY`·`NO_USER_ACTION`).

| action | 주요 필드 |
|---|---|
| `status` | `state`(listening/stopped), `browser`, `ws`, `tabs[]{index,url,title}` |
| `snapshot` | `frames`, `fields`, `draft_summary{text,select,checkbox_enum,radio_enum,date_tab_commit,repeat_row,hooks,widgets}`, `frame_urls[]`, `net`, `opened_tab`, `closed_tab` |
| `watch` | `stop_reason`(timeout/stop_file/page_closed), `pages`, `events{click,change,…}`, `actions`, `net`, `posts[]{method,url,status,event_target}`, `diff{added,removed}`, `values_recorded` |
| `draft` | `out`, `draft_summary`, `lines` |
| `diff` | `n_added`, `n_removed`, `added[]`, `removed[]` |

## 파일 구성

- `.claude/skills/build_webauto/SKILL.md` — 이 문서. `references/runbook.md` — 전제·판정 기준·귀속 체크리스트·러너 계약·에러 대응.
- `probes/web_probe.py` — 범용 정탐 CLI(조립·출력만). `probes/fixtures/web_form_fixture.html` — 오프라인 검증용 모사 폼.
- `web_core/cdp_channel.py`(채널 attach) · `page_inventory.py`(인벤토리 JS·초안·diff) · `probe_kit.py`(실행 골격·네트워크·실연 기록) ·
  `tests/test_page_inventory.py`(순수 로직 테스트).
- 산출: `probes/out/<action>_<key>_<ts>/{inventory.json, shot.png, fieldmap.draft.yaml, net.json, events.jsonl, actions.json,
  inventory_before/after.json, diff.json, steps.jsonl}` (gitignore).

## 이력

- 2026-10-06 신설(사용자 요청 — "다른 웹사이트도 정탐 후 자동화 스크립트를 만들려고 한다, 입력 스킬을 만들려면 정탐하고 실행기를
  생성해야 한다"). 범용 정탐(`web_probe`)·실연 캡처(`watch`)·공용 계층 `web_core` 를 함께 도입. 러너 뼈대 자동 생성은 첫 실제 대상으로
  검증한 뒤 추가한다(spec_아키텍처 ④).

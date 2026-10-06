# build_webauto runbook — 전제·판정 기준·귀속 체크리스트·러너 계약·에러 대응

명령·옵션은 [SKILL.md](../SKILL.md) 표가 유일본이다(§6 검증 절차의 재현용 명령만 예외). 아키텍처 규칙의 원본은 [CLAUDE.md](../../../../CLAUDE.md), 결정 이력은
[spec_아키텍처.md](../../../../spec/spec_아키텍처.md). 여기에는 판단에 필요한 기준만 둔다.

## 1. 전제

| 항목 | 조건 | 확인 |
|---|---|---|
| CDP 채널 | 대상 사이트 SSO 경계의 채널(포트 + 전용 프로필)이 떠 있음 | `status` → `state: listening` |
| 채널 정의 | spec_아키텍처 ② 채널 표에 행이 있음(없으면 먼저 추가) | 포트를 `--port` 로 넘긴다(기본값 없음) |
| 로그인 | 사용자가 그 채널 브라우저에서 직접 로그인 | `snapshot --wait-ready <폼 고정 셀렉터>` 로 대기 가능 |
| Python | 3.12 + playwright(브라우저 다운로드 불필요 — `connect_over_cdp`) | `python -c "import playwright"` |
| 사용자 입회 | `watch` 는 사용자가 그 시간 동안 직접 조작 | 시작 전 안내, 끝나면 `STOP` |

## 2. 결과 판정 기준

**snapshot**
1. `ok: true`, `fields > 0`(0 이면 `PROBE_EMPTY` — 성공 아님).
2. `frame_urls` 에 폼 본체 프레임이 보이고, `draft_summary` 의 primitive 합계가 `shot.png` 의 입력 칸 수와 대략 맞다.
3. 초안 `frame.anchor` 가 "후보" 면 폼에 늘 있는 고정 컨트롤(제목·폼 id 등)로 바꿔 `draft --anchor` 로 다시 만든다.
4. `prefix` 가 비어 있으면 ASP.NET 이 아닌 사이트다 — 셀렉터가 `#id` 그대로인지, id 가 매번 바뀌는(동적 id) 사이트인지 두 번
   찍어 비교한다(동적이면 name·라벨·구조 셀렉터가 필요 → hooks/core).

**watch**
1. `ok: true`(사용자 조작 ≥ 1). `stop_reason` 이 `page_closed` 면 끝 인벤토리·diff 가 없다.
2. `actions.json` 의 순서가 사용자가 말한 시연 순서와 맞다. 팝업이 열렸으면 `page_open` 과 그 뒤 `page` 번호가 바뀐 행이 있다.
3. 저장을 눌렀다면 `posts[]` 에 저장 후보 요청이 있다(ASP.NET 은 `event_target` 이 저장 버튼 id). 없으면 저장이 XHR 이 아닌
   다른 경로(새 창·form target)였는지 `events.jsonl` 의 `navigate` 로 본다.
4. `diff.added` 에 `…_ctlNN_…` 이 늘었다면 행추가 postback(→ `repeat_row`), 팝업 선택 뒤 readonly 칸이 채워졌다면 계산/팝업 값
   (→ hook 후보)이다.

## 3. 귀속 체크리스트(정탐 → recipe)

- [ ] `<그룹>/<코드>_recipes/<unit>/fieldmap.yaml` — 초안 복사, `draft: true` 제거, `source:` 를 template 키로, 헤더에 출처
      inventory 경로·실측일. 손으로 지어낸 셀렉터 없음(전부 inventory/실연에서 나온 것).
- [ ] `input.template.yaml` — 항목마다 주석: 출처(사용자 자료의 어디), 선택 기준, 검증 규칙(형식·필수·범위), `gate_ref`(workflow 게이트).
      사실이 없으면 비워 두고 묻는다(임의 생성 금지).
- [ ] `context.md` — 진입 경로(URL·메뉴), 로그인/세션 단계, 데이터 원천, 채움 순서·위젯 처리(실연 `actions.json` 근거), 저장 흐름
      (`net.json` 근거), 쓰기 경계(임시저장까지, 상신 금지).
- [ ] `references/<시스템>/` — 사이트 동작·제약(진입 정책, 세션 규칙, 문서번호 선채번 같은 부작용, API 스펙).
- [ ] `spec/spec_<주제>.md` — ① 요청 ② 확정 사양 ③ 구현 상태 ④ 미결.

## 4. 러너 계약(primary runner 체크리스트)

원본은 CLAUDE.md "그룹의 5계층·primary 와 helper 경계·로그·감독 계약". 만들 때 확인만 한다:

- [ ] 위치 `<그룹>/runners/<unit>.py`, workflow task 와 1:1, 다른 primary 를 import 하지 않음(공용부는 core).
- [ ] CLI: `--input <코드>_inputs/…yaml`(필수), `--purpose`(목적 여럿일 때), 기본 dry-run, 저장은 opt-in(`--save` 등), 기존 레코드
      덮어쓰기는 별도 명시 플래그. `--help` 는 브라우저·네트워크 없이 로드.
- [ ] 입력 검증(validate 게이트) → 채널 attach(`web_core.cdp_channel`) → 크롬 채널 파일락 → 세션 판정(wait_user 면 중단) →
      fieldmap 대로 주입 → postcondition 확인 → (opt-in 시) 임시저장 → 결과 캡처.
- [ ] stdout JSON 1개, `logs/<러너>/<일시_키>/steps.jsonl` + `final.json`(verdict ok|retry|fail|wait_user), 미등록 에러는 중단.
- [ ] 상신·제출·삭제 코드 경로 없음(workflow `gates.forbidden`).
- [ ] 테스트: `<코드>_core/tests/`(순수 로직), `runners/tests/`(`--help`·dry-run·입력 검증).

## 5. 에러·상태 대응

| 결과 | 뜻 | 대응 |
|---|---|---|
| `error: 포트 미지정` (exit 1) | `--port`·`CDP_PORT` 없음 | spec ② 채널 표에서 포트 확인. 없으면 절차 2(채널 생성) |
| `state: stopped` (exit 2) | 포트에 Chrome 없음 | `set_cdp_chrome launch <port>` 또는 바탕화면 아이콘 |
| `state: no_tab` (exit 2) | `--tab` 일치 탭 없음 | `status` 의 `tabs[]` 를 보고 부분문자열을 고친다 |
| `state: wait_user` (exit 3) | `--wait-ready` 셀렉터 미등장 | 사용자가 로그인·화면 이동 후 재실행. 셀렉터가 맞는지 snapshot 으로 확인 |
| `PROBE_EMPTY` (exit 6) | 컨트롤 0건 | 로딩 전·교차 출처 프레임 접근 실패·canvas 화면. `shot.png`·`steps.jsonl` 확인 |
| `NO_USER_ACTION` (exit 6) | 기록된 조작 0건 | 다른 탭에서 조작했거나 시간 밖. 팝업 창에서만 조작했다면 그 창이 기록 시작 후 열렸는지 확인 |
| 실연 중 다이얼로그 | `watch` 는 다이얼로그를 기록만 하고 응답하지 않는다 | 사용자가 브라우저에서 직접 확인/취소. 자동 닫힘 없음(2026-10-06 headless 검증) — 실제 창(headed)에서 첫 사용 때 확인 버튼이 눌리는지 확인하고 이 줄을 갱신 |
| 같은 탭 반복 watch | 이전 실행의 리스너가 남아 있음 | 옵션(`--values`)은 실행마다 갱신된다. 이벤트 중복이 의심되면 탭을 새로고침 후 재실행 |

## 6. 검증 절차

- **순수 로직**: `python web_core/tests/test_page_inventory.py` · `python ea_approval/ea_core/tests/test_inventory.py`.
- **오프라인 폼**(임시 채널 — 사용자 채널을 쓰지 않는다): 예비 포트로 headless Chrome 을 scratch 프로필로 띄운 뒤
  `snapshot --port <예비> --url file:///<루트>/probes/fixtures/web_form_fixture.html` → frames 2 · fields 7 · text 3 · select 1 ·
  checkbox_enum 1. `watch` 는 별도 playwright 클라이언트가 사용자 역할(입력·선택·체크·iframe 입력·저장 confirm 수락)을 하게 해
  click/key/change/dialog 기록, 마스킹(입력값 미기록)·`--values`(입력값 기록)를 확인한다(2026-10-06 통과).

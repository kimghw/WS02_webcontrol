---
name: probe_eclass
description: KRS eclass 전자결재(e-Approval)를 CDP 로 읽기 전용 정탐해 자동 폼 기입에 필요한 원자료를 만든다 — 크롬 채널·세션 상태 확인(status), 결재양식함의 양식 FORMID 카탈로그(forms), 지정 양식의 프레임·컨트롤 인벤토리+캡처+요청/응답(form), 사용자가 보고 있는 화면 캡처(snapshot), fieldmap DSL v1 초안(draft). "eclass 양식 뭐 있어", "이 폼 필드 뽑아줘/탐색해줘", "전자결재 폼 자동 기입 준비", 결재 폼 구조·셀렉터 파악, 정탐 결과로 recipe(fieldmap·input.template) 만들기 요청 시 사용. 저장·상신·삭제·실값 주입, 로그인/OTP 자동 통과, eclass 외 시스템에는 쓰지 않는다.
argument-hint: "[status | forms | form <FORMID> [--net] | snapshot [<탭 부분문자열>] | draft <inventory.json> | help] [--port N]"
---

# probe_eclass — eclass 전자결재 정탐(읽기 전용)

자동 폼 기입(러너)을 만들기 전에 **"어디에 무엇이 있나"** 를 실측하는 스킬이다. 사용자가 CDP 채널로 띄운
Chrome(로그인 세션 그대로)에 붙어 결재양식함의 양식 목록(FORMID), 양식 하나의 프레임/컨트롤 구조, 열린 화면의
스냅샷을 JSON·PNG 로 남기고, 그것을 fieldmap DSL v1 **초안** 으로 바꿔 준다. 초안은 사람이 검토해
recipe(`fieldmap.yaml`·`input.template.yaml`·`context.md`)로 승격한다 — 정탐 자체는 아무것도 저장·상신하지 않는다.

> 위치: `build_webauto`(웹 자동 입력 만들기 — 절차 ① create) 의 **eclass 전용 정탐 어댑터**다. 범용 정탐·사용자 실연 캡처
> (`watch`)는 `probes/web_probe.py` 가 하고, 이 스킬은 eclass 고유 부분(세션 단계 판정·성명 핸드셰이크·loginbyname 진입·
> 결재양식함 FORMID 카탈로그·eclass 초안 절)을 맡는다. eclass 폼의 실연 캡처는 이 스킬로 폼을 연 뒤
> `web_probe watch --port <eclass 채널 포트 — spec ② 채널 표> --tab DocumentView` 로 한다(web_probe 는 `ECLASS_CDP_PORT` 를 읽지 않는다).
>
> 배치(CLAUDE.md 규약): 이 스킬 폴더에는 절차 문서만 있다. 실행체는 정탐 스크립트 `probes/ea_eclass_probe.py`
> (읽기 전용, stdout JSON 1개)이고, 엔진은 공용 계층 `web_core/`(채널 attach·범용 인벤토리·정탐 키트) + ea 그룹 core
> `ea_approval/ea_core/`(eclass 세션 판정·카탈로그·초안 어댑터)다. 정탐은 working unit 이 아니므로 primary runner·workflow.yaml 이 없다.

```
python "<프로젝트 루트>/probes/ea_eclass_probe.py" <action> [옵션]
```

| action | 동작 | 부작용 |
|---|---|---|
| `status [--port]` | `/json/version` 생존 + 열린 탭 분류(eapproval/docview/login/…) + 세션 힌트. playwright 불필요 | 없음 |
| `forms` | 결재양식함(양식선택) 링크 → `{form_id, label, category, url}` 카탈로그 (`forms.json`) | e-Approval 탭이 없으면 새 탭을 열었다가 닫는다(`--keep` 로 유지) |
| `form --form-id <FORMID>` | 양식을 `loginbyname?ReturnUrl` 경유로 새 탭에 열어 프레임/컨트롤 인벤토리 + 전체 캡처 + (`--net`) 요청/응답 + 초안 | 새 탭 열기·닫기, 성명 핸드셰이크 1회(`--ea-name`/`KRS_EA_NAME` 있을 때만). **문서번호가 선채번되므로 필요 이상 열지 않는다** |
| `snapshot [--tab 부분문자열 \| --url U]` | 지금 사용자가 보고 있는 탭(기본: docview > e-Approval > eclass 순)의 인벤토리 + 캡처 + 초안. `--url` 이면 새 탭 | 기존 탭은 건드리지 않음(`--url` 탭만 닫음) |
| `draft --inventory <inventory.json>` | 인벤토리 → `fieldmap.draft.yaml` (오프라인, 브라우저 불필요) | 파일 1개 |
| `help` | action·옵션 표 | 없음 |

옵션: `--port N`(기본 `ECLASS_CDP_PORT` > 9333) · `--env FILE`(기본 루트 `.env.eclass` — `ECLASS_CDP_PORT`,
`KRS_EA_NAME`; 값은 절대 출력하지 않는다) · `--out DIR` · `--keep` · `--net` · `--wait-user SEC`(기본 45 —
로그인/성명/OTP 를 사용자가 처리할 때까지 대기) · `--ea-name 성명` · `--polls N`.

## 인자

| 인자 | 동작 |
|---|---|
| `help` / `-h` / `--help` | 이 인자 표와 action 표만 출력하고 종료 |
| (없음) | `status` → 채널이 살아 있고 e-Approval 탭이 있으면 `forms` 까지 이어서 보고, 아니면 status 결과와 다음 행동만 |
| `status` / `forms` | 위 표 |
| `form <FORMID>` | FORMID 는 `forms` 결과 또는 [references/eclass/eclass_eapproval_tour.md](../../../references/eclass/eclass_eapproval_tour.md) §2 표에서 고른다. 모르면 사용자에게 양식명을 물어 표에서 찾는다(임의 추측 금지) |
| `snapshot [<부분문자열>]` | 사용자가 "지금 이 화면" 을 캡처해 달라고 할 때. 부분문자열은 탭 URL/제목 |
| `draft <경로>` | 이미 있는 inventory.json 으로 초안만 다시 만들 때 |

## 절차

1. **채널·세션 확인** — `status`. `state: stopped` 면 `set_cdp_chrome launch <port>`(또는 바탕화면 아이콘)로
   채널을 띄우게 하고 멈춘다. `session_hint: needs_login` 이면 사용자가 브라우저에서 로그인하도록 안내한다
   (자격증명은 이 스킬이 다루지 않는다).
2. **FORMID 확정** — 사용자가 양식명만 말했으면 `forms`(또는 references §2 표)에서 FORMID 를 찾는다. 카탈로그가
   references 표와 다르면(양식 추가·삭제) references 를 갱신한다.
3. **폼 정탐** — `form --form-id <FORMID> --net`. 결과 `state` 가
   - `ok` → 4 로. `ready.toolbar/form` 이 false 면 폼이 늦게 떴거나 프레임 구조가 다른 것이므로 `shot.png` 를 열어
     확인하고 `--polls 80` 으로 한 번 더.
   - `needs_name`/`needs_login`/`needs_otp`/`needs_device_auth`(exit 3) → 탭이 열린 채 남아 있다. 사용자가 그
     탭에서 처리한 뒤 같은 명령을 재실행한다. 성명 핸드셰이크는 `.env.eclass` 의 `KRS_EA_NAME` 이 있으면 자동.
   - `rejected`(exit 4) → `message` 를 보고. loginbyname 경유가 아닌 URL 을 넣었거나 권한 문제.
   - `PROBE_EMPTY`(exit 6) → 폼 미로딩/차단. 캡처를 열어 원인을 본다.
4. **초안 검토** — `fieldmap.draft.yaml` 을 읽고 (a) `prefix`·`frame.anchor` 가 맞는지 (b) 각 필드의 primitive 가
   위젯과 맞는지(라벨이 비어 있으면 `shot.png` 와 대조) (c) `repeat_rows.add_anchor` 후보가 어느 표의 행추가인지
   (d) `hooks_후보`·`editor`(DEXT5 본문)가 DSL 밖임을 사용자에게 알린다. 초안은 정본이 아니다 — 러너가 읽게 하지 않는다.
5. **귀속** — 확정 사실만 옮긴다: 폼 구조·셀렉터 → 그 working unit 의 recipe(`ea_approval/ea_recipes/<unit>/`,
   초안을 복사해 `source:` 를 채우고 헤더에 출처 inventory 경로·실측일을 남긴다), 시스템 동작·제약 → `references/eclass/`,
   결정·상태 → `spec/spec_아키텍처.md` ②③. `probes/out/` 원자료는 gitignore 라 그대로 둔다.
6. **보고** — 아래 형식.

## 보고 형식

```
채널 <port>: listening | stopped   세션: ok | needs_login | needs_name | …
양식: <FORMID> <양식명>  (카탈로그 N건)
프레임 M개 · 컨트롤 K개 · 툴바/폼 프레임: 확인 | 미확인
산출: probes/out/<run>/{inventory.json, shot.png, fieldmap.draft.yaml[, net.json]}
초안 요약: text n · select n · checkbox_enum n · date n · repeat_row n · hooks_후보 n · 본문 편집기 있음/없음
다음: recipe 승격(unit 이름) | 사용자 조치(로그인/성명) | 재실행
```

한 줄씩만. JSON 을 그대로 되풀이하지 않는다. 열어 둔 탭이 있으면(`wait_user`, `--keep`) 그 사실을 적는다.

## 판단 규칙

- **읽기 전용은 타협하지 않는다.** 정탐은 저장·상신·삭제·행추가·첨부 어느 것도 클릭하지 않는다. 사용자가
  "채워서 저장까지" 를 원하면 그것은 러너(working unit)의 일이므로 절차 5 에서 recipe 를 만든 뒤 별도 작업으로 넘긴다.
- **로그인·OTP·기기인증은 사용자 직접.** 스크립트는 상태만 보고(`wait_user`, exit 3)하고 탭을 열어 둔다.
  gate 자격증명을 스크립트에 넣지 않는다. 허용된 유일한 입력은 RealEANet 성명 핸드셰이크뿐이다.
- **진입은 loginbyname 경유.** DocumentView 직접 URL 을 `--url` 로 넣으면 로그인된 세션에서 MsgBox 거부가 난다
  (references §3). `--form-id` 를 쓰면 스크립트가 올바른 진입 URL 을 만든다.
- **문서번호 선채번.** 폼을 여는 것만으로 `DOCID=HER-…` 가 부여된다(references §5). 같은 양식을 반복 정탐하지
  말고 `inventory.json` 을 재사용(`draft`)한다.
- **채널은 하나.** 기본 9333 은 원형 프로젝트(krs-web-agents) KRS 채널과 같은 프로필을 쓴다. 다른 채널을 쓰면
  `spec/spec_아키텍처.md` ② 채널 표를 먼저 고치고 `--port`/`ECLASS_CDP_PORT` 로 맞춘다.
- **실값·개인정보.** 인벤토리는 컨트롤의 값을 담지 않지만(select/checkbox 선택값·라벨만) 캡처와 `net.json` 에는
  사용자 이름·문서번호가 남는다. 전부 `probes/out/`(gitignore)에만 두고 외부 공유 전 마스킹한다.
- **eclass 외 화면**(`state: not_eclass`)도 `snapshot` 은 인벤토리를 뽑아 주지만 세션 판정·초안 접두 규칙은 eclass
  전용이므로 그 결과를 다른 시스템 recipe 에 그대로 쓰지 않는다.

## JSON 필드

공통: `ok`, `action`, `port`, `state`, `hint`, `out`(출력 폴더), `files{}`, 오류 시 `error`.
exit 0 성공 / 1 오류 / 2 채널·대상 없음 / 3 wait_user / 4 진입 거부 / 6 수집 0건.

| action | 주요 필드 |
|---|---|
| `status` | `state`(listening/stopped), `browser`, `ws`, `session_hint`(needs_login/eapproval_open/eclass_open/no_eclass_tab), `tabs[]{index,kind,url,title}` |
| `forms` | `count`, `tabs[]`(카테고리), `forms[]{form_id,label,category,visible,url}`, `opened_tab`, `closed_tab` |
| `form` | `form_id`, `url`, `ready{toolbar,form}`, `frames`, `fields`, `draft`, `frame_urls[]`, `dialogs[]`, `handshake_tried`, `closed_tab` |
| `snapshot` | `form` 과 같음 + `catalog_forms`(양식선택 화면이면), `opened_tab` |
| `draft` | `inventory`, `out`, `form_frame`, `lines` |

## 파일 구성

- `.claude/skills/probe_eclass/SKILL.md` — 이 문서. `references/runbook.md` — 전제·검증 기준·에러 대응·샌드박스 검증.
- `probes/ea_eclass_probe.py` — 정탐 CLI(조립·출력만). `probes/fixtures/eclass_form_fixture.html` — 오프라인 검증용 모사 폼.
- `web_core/`(공용 — `cdp_channel.py` 채널 attach · `page_inventory.py` 인벤토리 JS·범용 초안 · `probe_kit.py` 실행 골격·네트워크 캡처).
- `ea_approval/ea_core/eclass_session.py`(세션 판정·진입 URL·성명 핸드셰이크·채널 포트) · `eclass_inventory.py`(카탈로그 파싱·
  폼/툴바 프레임·eclass 초안 어댑터) · `tests/test_inventory.py`(순수 로직 테스트).
- `references/eclass/eclass_eapproval_tour.md` — 프레임 구조·FORMID 카탈로그·진입 정책·툴바 버튼 실측.
- 산출: `probes/out/<action>_<key>_<ts>/{inventory.json, shot.png, fieldmap.draft.yaml, forms.json, net.json, steps.jsonl}` (gitignore).

## 이력

- 2026-09-30 신설(사용자 요청 — "eclass 에서 자동 form 기입을 위해 탐색하는 스킬, CDP 로"). 실사이트 검증: 카탈로그 43건,
  `KR_EA_Form2_Test` 11프레임·54컨트롤·초안 생성. 샌드박스(Windows Sandbox, 호스트 Python/Chrome 매핑) 검증 절차는 runbook.
- 2026-10-06 범용 부분을 공용 계층 `web_core/` 로 승격하고(`ea_core/cdp_channel.py` 제거) `build_webauto` 의 eclass 어댑터로 위치를
  정함. CLI·출력은 그대로, `--net` 의 POST 본문은 키 이름 + `__EVENTTARGET` 만 기록하도록 바뀜(값 마스킹).

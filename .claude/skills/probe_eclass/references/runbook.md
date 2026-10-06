# probe_eclass runbook — 전제·검증 기준·에러 대응

명령·옵션은 [SKILL.md](../SKILL.md) 의 표가 유일본이다(§4 절차 예시·§5 검증 절차의 재현용 명령만 예외). 여기에는 전제, 산출물 판정 기준, 에러 대응, 검증 절차만 둔다.

## 1. 전제

| 항목 | 조건 | 확인 |
|---|---|---|
| CDP 채널 | Chrome 이 `--remote-debugging-port=<port>` + 전용 프로필로 떠 있음(기본 9333) | `status` → `state: listening` |
| 로그인 2층 | ① eclass 포털(gate SSO) 로그인 ② RealEANet 성명 핸드셰이크 | `status.session_hint` / `form.state` |
| Python | 3.12 + playwright(1.55 실측) — 브라우저 다운로드 불필요(`connect_over_cdp`) | `python -c "import playwright"` |
| 채널 정의 | `spec/spec_아키텍처.md` ② 채널 표 — 포트·프로필 | 포트가 다르면 `--port`/`ECLASS_CDP_PORT` |
| 비밀 | `.env.eclass`(gitignore)에 `KRS_EA_NAME`(성명)만. gate ID/PW 는 두지 않는다 | 스크립트는 키 이름만 출력 |

## 2. 산출물 판정 기준

`form`/`snapshot` 결과를 "성공" 으로 보려면 모두 만족해야 한다:

1. `ok: true`, `state: ok`, `fields > 0` (0 이면 `PROBE_EMPTY` — 성공으로 치지 않는다).
2. `ready.toolbar` 와 `ready.form` 이 모두 true(DocumentView 인 경우). 하나라도 false 면 `shot.png` 로 원인 확인.
3. `frame_urls` 에 `Forms/Drafts/<FORMID>.aspx`(폼 본체)와 `toolbar` 가 보인다.
4. `fieldmap.draft.yaml` 의 `frame.anchor` 줄에 "앵커 미발견" 주석이 없고 `prefix` 가 비어 있지 않다.
5. 초안의 필드 수가 `shot.png` 에서 눈으로 세는 입력 칸 수와 대략 맞다(라벨 공백은 허용 — 휴리스틱).

`forms` 는 `count > 0` 이고 카테고리 탭이 2개(기안문·양식결재)이면 정상. 43건(2026-09-30)과 크게 다르면 권한/화면 변경.

## 3. 에러·상태 대응

| 결과 | 뜻 | 대응 |
|---|---|---|
| `state: stopped` (exit 2) | 포트에 Chrome 없음 | `set_cdp_chrome launch <port>` 또는 바탕화면 아이콘. 9333 이 원형 프로젝트 채널이면 그 아이콘 |
| `session_hint: needs_login` / `state: needs_login` (exit 3) | gate/eclass 로그인 화면 | 사용자가 열린 탭에서 로그인. 스크립트는 자격증명을 넣지 않는다 |
| `state: needs_name` (exit 3) | RealEANet 성명 입력 화면 | 탭에서 성명 입력 후 재실행, 또는 `.env.eclass` 의 `KRS_EA_NAME`/`--ea-name` |
| `needs_otp` / `needs_device_auth` (exit 3) | OTP·PC 인증 | 사용자 직접. 절대 자동 통과 시도 금지 |
| `state: rejected` (exit 4) | MsgBox("상신하실 수 없습니다…") | DocumentView 직접 진입이었는지 확인 → `--form-id` 로 재실행. 계속되면 권한 문제로 사용자에게 |
| `no_catalog_frame` (exit 2) | 양식선택 프레임 없음 | e-Approval 좌측 메뉴 "결재양식함" 을 열고 `forms` 재실행 |
| `PROBE_EMPTY` (exit 6) | 컨트롤 0건 | 폼 미로딩·차단·프레임 접근 실패. `shot.png`·`steps.jsonl` 확인, `--polls 80` 재시도 |
| `ImportError … _greenlet` (exit 1) | playwright 의존 DLL 없음 | VC++ 재배포(`msvcp140.dll`) 설치. 샌드박스면 §5 |
| `TimeoutError` (exit 1) | goto 45초 초과 | 네트워크/VPN 확인 후 재실행 |
| 탭이 남아 있음 | `wait_user` 또는 `--keep` | 사용자 조치 후 재실행하면 새 탭으로 진행. 남은 탭은 사용자가 닫는다 |

## 4. 조작 전/후 스냅샷 절차

러너가 재현해야 할 조작(팝업 선택, 행추가 뒤 상태)을 사용자가 직접 시연할 때:

1. 사용자가 브라우저에서 화면을 원하는 상태로 만든다(예: 행 2개 추가된 구매요청서).
2. `snapshot --tab DocumentView` — 그 탭을 건드리지 않고 인벤토리·캡처. 조작 전/후 두 번 찍어 `inventory.json` 을
   비교하면 postback 으로 늘어난 컨트롤(`…_ctl02_…`)과 앵커가 드러난다.
3. `--net --net-seconds 10` 을 붙이면 그 시간 동안의 XHR/postback 요약이 `net.json` 에 남는다(사용자는 그 사이에 조작).
4. 조작 순서 자체(클릭·선택·팝업·다이얼로그)가 필요하면 `python probes/web_probe.py watch --port <eclass 채널 포트> --tab DocumentView` 로
   사용자 실연을 기록한다(판정 기준은 build_webauto runbook §2). 전/후 인벤토리 비교는 `web_probe diff`.
5. 차이를 recipe(`repeat_row`·`postcondition`)와 references 에 귀속한다.

## 5. 검증 절차

- **순수 로직**: `python ea_approval/ea_core/tests/test_inventory.py` (브라우저 불필요, 10건) + 공용
  `python web_core/tests/test_page_inventory.py`.
- **오프라인 폼**: `snapshot --url file:///<루트>/probes/fixtures/eclass_form_fixture.html --wait-user 0` →
  초안에 `date_tab_commit`·`checkbox_enum`·`repeat_row`·`LinkButton1`·`prefix: "#ctl00_ContentPlaceHolder_Content_"` 가 있어야 한다.
- **실사이트(읽기 전용)**: `forms` → 43건 안팎, `form --form-id KR_EA_Form2_Test`(테스트 기안문) → 11프레임·54컨트롤(2026-09-30).
- **Windows Sandbox**(자격증명 없는 깨끗한 PC 재현, 2026-09-30 실행): `wsb share` 로 호스트 Python 폴더(RO)·Chrome 폴더(RO)·
  프로젝트(RO)·결과 폴더(RW)를 매핑하고, 결과 폴더의 `.ps1` 을 `wsb exec … -File` 로 실행한다. greenlet 이 `msvcp140.dll` 을
  요구하므로 호스트 `System32` 의 `msvcp140.dll`·`vcruntime140*.dll` 을 결과 폴더에 복사해 두고 샌드박스 `System32` 에
  넣는다. 기대 결과: unittest 통과, 죽은 포트 exit 2, fixture 스냅샷 ok, 공개 로그인 페이지 스냅샷 `state: needs_login` +
  `tbUserId` 검출, `forms`/`form` 은 `needs_login`(exit 3) 으로 멈춤. 샌드박스 환경 제약(WMI 거부·exec 출력 없음)은
  `set_cdp_chrome` 스킬의 샌드박스 메모와 같다.

---
name: set_cdp_chrome
description: CDP(Chrome DevTools Protocol) 접속용 Chrome 채널(포트 + 전용 프로필)을 더블클릭 한 번으로 띄우는 전용 바탕화면 아이콘(바로가기)을 만들고 관리한다 — 뱃지 아이콘 + --remote-debugging-port + --user-data-dir 바로가기 생성(add), 채널 현황(list), 생존 확인(status), 기동·종료(launch/stop), 제거(remove). Chrome 136+ 는 기본 프로필에서 원격 디버깅을 막으므로 전용 프로필 방식이 필수다. "CDP 크롬 아이콘/바로가기 만들어", 원격 디버깅(9222 등) 크롬 띄우기·살아있는지 확인·끄기, Playwright connect_over_cdp 로 붙을 크롬 준비, 웹 자동화 프로젝트의 채널(포트+프로필) 세팅 요청 시 사용. 크롬 자동화 코드 자체 작성(접속 예시는 references 만 참고), 크롬 확장 개발, Claude in Chrome 확장, 원격 PC 의 크롬에는 쓰지 않는다.
argument-hint: "[add [<port>] [-Name ..] [-StartMenu] [-Launch] [-DryRun] | list | status [<port>] | launch [<port>] | stop [<port>] | remove [<port>] [-Purge] | path | help]"
---

# set_cdp_chrome — CDP 접속용 Chrome 채널 아이콘 생성·관리

프로젝트 규약에서 **채널 = 포트 + 전용 프로필**이다. 이 스킬은 채널 하나를 바탕화면 아이콘 하나로 만든다:
Chrome 로고에 `CDP` 뱃지를 얹은 전용 아이콘, `--remote-debugging-port=<포트>` + `--user-data-dir=<전용 프로필>` 로
Chrome 을 여는 바로가기. 사용자는 아이콘을 더블클릭해 채널을 띄우고, 러너·정탐 스크립트는
`http://127.0.0.1:<포트>` 에 `connect_over_cdp` 로 붙는다. 만든 채널의 현황·생존 확인·기동·종료·제거까지 같은
스크립트로 처리한다.

> 부작용: 바탕화면/시작 메뉴에 `.lnk` 생성·삭제, `%LOCALAPPDATA%\ChromeCDP\{icons,profiles}\` 생성, `launch`/`stop`
> 은 Chrome 프로세스 기동·종료. 결과 검증은 호출 시점 코드 에이전트의 책임이다.

모든 파일·프로세스 작업은 `scripts/set_cdp_chrome.ps1` 이 한다(**stdout JSON 1개**, `help` 만 텍스트).
직접 `.lnk` 를 만들거나 `taskkill` 을 치지 않는다.

```
powershell -NoProfile -ExecutionPolicy Bypass -File "<이 SKILL.md 가 있는 폴더>/scripts/set_cdp_chrome.ps1" <action> [port] [옵션]
```

| action | 동작 |
|---|---|
| `add [port]` | 뱃지 아이콘(.ico 256/64/48/32/16px + .png 미리보기) → 프로필 폴더 → 바탕화면 `.lnk`. 같은 포트가 다른 이름으로 이미 있으면 `state: conflict` 로 거부 |
| `list` | 바탕화면·시작 메뉴의 CDP 바로가기 전부(`managed`/unmanaged 구분)와 포트 상태 |
| `status [port]` | 생존 확인 `GET /json/version` → `browser`·`ws`·`targets`(열린 탭). 죽어 있으면 `ok:false, state:stopped`(exit 2) |
| `launch [port]` | 바로가기에 기록된 것과 같은 인자로 기동 후 최대 `-TimeoutSec`(20초) 대기. 이미 떠 있으면 `already-listening` |
| `stop [port]` | 그 포트를 가진 chrome.exe **브라우저 프로세스만** 종료(일반 Chrome 무관) |
| `remove [port]` | managed 바로가기 + 아이콘 삭제, 프로필은 유지. `-Purge` 면 프로필까지(Chrome 이 떠 있으면 거부) |
| `path` | 사용할 chrome.exe 경로 |

옵션: `-Name "표시이름"` · `-StartMenu`(시작 메뉴에도) · `-NoDesktop`(시작 메뉴만) · `-Launch`(만든 뒤 기동·검증) ·
`-DryRun`(add/remove 계획만) · `-Label`/`-Color`(뱃지 글자·색, 기본 `CDP`/`#7C3AED`) · `-ProfileDir` · `-ChromePath` ·
`-ExtraArgs "--lang=ko","--window-size=1280,900"` · `-AllowOrigins` · `-Force` · `-Headless`(launch, 테스트용).
`status`/`launch`/`stop`/`remove` 에 포트를 생략하면 managed 바로가기가 정확히 1개일 때 그 포트, 아니면 9222.

## 인자

| 인자 | 동작 |
|---|---|
| `help` / `-h` / `--help` | 이 인자 표와 action 표만 출력하고 종료 |
| (없음) | `list` → 채널이 하나도 없으면 사용자가 아이콘을 원해서 부른 것이므로 곧장 `add 9222`, 있으면 현황만 보고 |
| `add [<port>] [옵션]` | 아래 "절차" |
| `list` / `status` / `path` | 읽기 전용. 파일을 바꾸지 않는다 |
| `launch` / `stop` | Chrome 기동·종료 |
| `remove [<port>] [-Purge]` | 아래 "절차 — 제거" |

## 절차

1. **포트 확정** — 사용자가 말한 포트 > 프로젝트 채널 표(`spec/spec_아키텍처.md` ② 또는 `port_manager`
   대장) > 기본 9222. 9222 가 다른 프로세스에 잡혀 있으면(`status 9222` 가 `port-in-use-by-other`)
   `port_manager suggest` 로 받는다. SSO 경계(도메인 묶음)마다 채널을 나누므로 시스템이 여럿이면 포트도 여럿이다.
2. **생성** — `add <port>`. 여러 채널을 운용하면 `-Name "Chrome CDP KRS (9333)"` 처럼 시스템명을 넣고, 검색으로
   띄우길 원하면 `-StartMenu`. 사용자가 바로 써보길 원하면 `-Launch`.
3. **검증** — 결과 JSON 의 `preview`(256px PNG)를 `Read` 로 열어 뱃지가 얹혔는지 보고, `shortcuts[]` 경로가
   존재하는지 확인한다. `-Launch` 였으면 `launch.state == listening` 과 `launch.ws` 를 확인한다.
4. **보고** — 아래 형식. 이어서 첫 실행 시 그 프로필에서 로그인이 필요하다는 점과, 채널 정의(포트·프로필)를
   프로젝트 바인딩 SSOT(채널 표)에 적어 두라는 점을 짚는다.

### 제거

1. `stop <port>` 로 내린다(떠 있으면 `-Purge` 가 거부된다).
2. `remove <port>` — 바로가기·아이콘만 지우고 프로필(로그인 상태·쿠키)은 남는다고 알린다.
3. 프로필까지 지우라고 사용자가 명시했을 때만 `remove <port> -Purge`. 애매하면 `AskUserQuestion` 으로 한 번 묻는다.

## 보고 형식

```
채널 <port>: 생성 | 이미 있음(conflict) | 제거
아이콘: Chrome CDP (<port>).lnk — 바탕화면[, 시작 메뉴]
프로필: %LOCALAPPDATA%\ChromeCDP\profiles\<port>  (첫 실행 시 로그인 필요)
접속: http://127.0.0.1:<port>  [ws=...  (launch 했을 때만)]
다음: 작업표시줄 고정은 우클릭 → 고정 · 채널 표에 포트/프로필 기록
```

한 줄씩만. JSON 을 그대로 되풀이해 출력하지 않는다.

## 판단 규칙

- **전용 프로필은 타협하지 않는다.** Chrome 136(2025-04)부터 기본 `User Data` 프로필에서는
  `--remote-debugging-port` 가 무시된다. "평소 쓰는 크롬에 포트만 붙여달라"는 요청에도 이 한계를 한 문장으로
  설명하고 전용 프로필로 진행한다(북마크·로그인은 그 프로필에서 다시). 개인 브라우징 프로필과 섞지 않는 것이
  프로젝트 규약이기도 하다.
- **포트 하나 = 채널 하나.** 같은 포트로 이름만 다른 바로가기를 또 만들면 어느 프로필이 뜨는지 헷갈리므로
  스크립트가 `conflict` 로 막는다. 사용자가 정말 원할 때만 `-Force`.
- **보안 기본값은 잠금.** 포트는 127.0.0.1 에만 열린다. `-AllowOrigins`(`--remote-allow-origins=*`)는 브라우저
  안에서 도는 CDP 클라이언트가 WebSocket 으로 붙어야 할 때만 쓰고, 그 경우 포트를 아는 어떤 웹페이지든 브라우저를
  조종할 수 있다고 알린다. Playwright·Puppeteer·Node/Python 클라이언트는 이 옵션 없이 붙는다.
- **`launch` 가 `not-answering` 이면** 같은 `--user-data-dir` 로 이미 Chrome 이 떠 있어 새 창만 열린 경우가
  대부분이다. `stop <port>` 후 재시도. 그래도 안 되면 그 프로필로 열린 Chrome 창을 사용자가 닫게 한다.
- **접속 코드 요청**(Playwright/Puppeteer/curl/WebSocket 예시)은 [references/cdp_connect.md](references/cdp_connect.md)
  를 읽고 그 스니펫을 준다. 코드 자체를 새로 설계하는 일은 이 스킬 범위 밖이다.

## JSON 필드

공통: `ok`, `action`, 선택적 `warnings[]`(치명적이지 않은 주의), `hint`(다음 행동), `error`. exit 0 성공 / 1 오류 / 2 없음·충돌·거부.

| action | 주요 필드 |
|---|---|
| `add` | `port`·`name`·`profile`·`icon`·`preview`·`shortcuts[]`·`args`·`endpoint`·`notes[]`·`dry_run`, `-Launch` 면 `launch{}` (아래 launch 필드) |
| `list` | `count`, `channels[]{port, state, managed, location, shortcut, profile, target, args, browser?, ws?}` |
| `status` | `state`(`listening`/`stopped`/`port-in-use-by-other`), `endpoint`·`browser`·`protocol`·`ws`·`targets[]{type,id,url,title}`, `pids[]` |
| `launch` | `state`(`listening`/`already-listening`/`not-answering`/`port-in-use-by-other`), `source`(`shortcut`/`defaults`), `chrome`·`args`·`pid` + status 필드 |
| `stop` | `state`(`stopped`/`still-listening`), `killed[]` |
| `remove` | `chrome_running`, `removed_shortcuts[]`·`removed_icons[]`·`removed_profiles[]`·`kept_profiles[]`, `-DryRun` 이면 `would_remove_*[]` |

## 플랫폼 주의 — Windows (이 PC)

- Windows PowerShell 5.1 용. PowerShell 도구에서는 `& "<폴더>\scripts\set_cdp_chrome.ps1" add 9222` 로 부른다.
- 바로가기 위치는 `[Environment]::GetFolderPath('Desktop')`(OneDrive 리다이렉트 포함)과 사용자 시작 메뉴
  `Programs`. 공용 바탕화면은 건드리지 않는다.
- **작업표시줄 고정은 스크립트로 불가**(Windows 10/11 정책) — 우클릭 → "작업 표시줄에 고정" 안내.
- 아이콘을 다시 만들었는데 탐색기가 옛 그림을 보여주면 아이콘 캐시다. 스크립트가 `SHChangeNotify` 를 보내지만
  안 바뀌면 탐색기 재시작/로그오프를 안내한다.
- Chrome 은 App Paths 레지스트리 → Program Files → LOCALAPPDATA 순으로 찾는다. 포터블 설치는 `-ChromePath`.

## 파일 구성

- `scripts/set_cdp_chrome.ps1` — 아이콘 렌더링(chrome.exe 아이콘 추출 + 뱃지 → PNG 프레임 ICO), `.lnk` 생성·스캔,
  생존 확인, 프로세스 종료. 본문은 ASCII 만(PowerShell 5.1 인코딩).
- `references/cdp_connect.md` — 만든 채널에 붙는 방법(HTTP 엔드포인트·Playwright·Puppeteer·순수 WebSocket)과
  자주 걸리는 문제. 접속 코드를 물을 때만 읽는다.
- 생성물: `%LOCALAPPDATA%\ChromeCDP\icons\chrome-cdp-<port>.ico|.png`, `%LOCALAPPDATA%\ChromeCDP\profiles\<port>\`,
  바탕화면(·시작 메뉴) `Chrome CDP (<port>).lnk`(Description 에 `set_cdp_chrome;port=<port>` 태그).

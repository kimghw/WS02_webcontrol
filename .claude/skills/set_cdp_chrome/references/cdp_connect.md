# CDP 접속 참고 — set_cdp_chrome 로 띄운 Chrome에 붙는 방법

`set_cdp_chrome add <port>` 로 만든 바로가기(또는 `launch <port>`)로 Chrome을 띄우면 `http://127.0.0.1:<port>` 에 DevTools 원격 디버깅 엔드포인트가 열린다. 아래는 그 엔드포인트에 붙는 대표적인 방법이다. 예시는 모두 기본 포트 9222 기준.

## 1. HTTP 엔드포인트 (상태 확인·탭 조작)

| 경로 | 용도 |
|:---|:---|
| `GET /json/version` | Chrome 버전, 프로토콜 버전, **브라우저 레벨** `webSocketDebuggerUrl` |
| `GET /json/list` (= `/json`) | 열린 타깃(탭·백그라운드 페이지) 목록, 각 타깃의 `webSocketDebuggerUrl` |
| `PUT /json/new?<url>` | 새 탭 열기 (Chrome 111+ 부터 PUT 필수) |
| `GET /json/activate/<id>` | 탭 앞으로 |
| `GET /json/close/<id>` | 탭 닫기 |
| `GET /json/protocol` | 이 Chrome이 지원하는 CDP 스키마 전체(JSON) |

```bash
curl -s http://127.0.0.1:9222/json/version
curl -s http://127.0.0.1:9222/json/list
curl -s -X PUT "http://127.0.0.1:9222/json/new?https://example.com"
```

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
Invoke-RestMethod http://127.0.0.1:9222/json/list | Format-Table type, url, id
```

주의: Host 헤더가 IP 또는 `localhost` 가 아니면 Chrome이 거부한다(DNS 리바인딩 방어). 항상 `127.0.0.1` 또는 `localhost` 로 부른다.

## 2. Playwright — 이미 떠 있는 Chrome에 붙기

Node:

```js
import { chromium } from 'playwright';

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const context = browser.contexts()[0];          // 사용자가 쓰고 있는 기본 컨텍스트
const page = context.pages()[0] ?? await context.newPage();
await page.goto('https://example.com');
// browser.close() 를 부르면 Chrome 자체가 닫힌다. 붙어 있던 연결만 끊으려면 프로세스를 그냥 끝낸다.
```

Python:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://example.com")
```

`connect_over_cdp` 는 사용자의 로그인 상태·확장 프로그램이 그대로 있는 실제 창을 조종한다. 브라우저를 새로 띄우는 `launch()` 와 달리 사람이 개입(캡차, 2FA)한 뒤 스크립트가 이어받는 흐름에 적합하다.

## 3. Puppeteer

```js
import puppeteer from 'puppeteer-core';

const browser = await puppeteer.connect({
  browserURL: 'http://127.0.0.1:9222',   // /json/version 을 읽어 WS URL을 알아낸다
  defaultViewport: null,                  // 창 크기를 그대로 사용
});
const [page] = await browser.pages();
await page.goto('https://example.com');
await browser.disconnect();               // close() 는 Chrome을 종료시킨다
```

## 4. 순수 WebSocket (라이브러리 없이)

브라우저 레벨 소켓(`/json/version` 의 `webSocketDebuggerUrl`)에는 `Target.*`, `Browser.*` 를, 탭 소켓(`/json/list` 의 각 항목)에는 `Page.*`, `Runtime.*`, `DOM.*` 를 보낸다. 메시지는 `{id, method, params}` JSON, 응답은 같은 `id` 로 돌아온다.

Python (`pip install websockets`):

```python
import asyncio, json, urllib.request, websockets

def targets(port=9222):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as r:
        return json.load(r)

async def main():
    page = next(t for t in targets() if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": "https://example.com"}}))
        print(await ws.recv())
        await ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": "document.title", "returnByValue": True}}))
        print(await ws.recv())

asyncio.run(main())
```

Node (내장 `WebSocket`, Node 22+):

```js
const { webSocketDebuggerUrl } = await (await fetch('http://127.0.0.1:9222/json/version')).json();
const ws = new WebSocket(webSocketDebuggerUrl);
ws.onopen = () => ws.send(JSON.stringify({ id: 1, method: 'Target.getTargets' }));
ws.onmessage = (e) => console.log(e.data);
```

## 5. 자주 걸리는 것

- **Chrome 136+ 기본 프로필**: `--remote-debugging-port` 가 무시된다. set_cdp_chrome 가 만든 바로가기는 항상 별도 `--user-data-dir` 를 쓰므로 이 문제가 없지만, 사용자가 직접 만든 바로가기가 기본 프로필을 가리키면 포트가 열리지 않는다.
- **같은 프로필로 이미 떠 있음**: 바로가기를 두 번 눌러도 Chrome은 기존 인스턴스에 새 창만 열어준다. 포트는 첫 인스턴스가 시작될 때의 인자로만 결정되므로, 인자를 바꿨다면 `set_cdp_chrome stop <port>` 후 다시 실행한다.
- **원격 PC에서 붙기**: 헤드 모드 Chrome은 127.0.0.1 에만 바인딩된다. 원격에서 쓰려면 SSH 포트포워딩(`ssh -L 9222:127.0.0.1:9222 user@host`) 같은 터널을 쓴다. 포트를 공개망에 노출하지 않는다.
- **브라우저 안에서 WebSocket 으로 붙는 클라이언트**(웹 기반 DevTools 프론트엔드 등)는 Origin 검사에 걸린다. 그때만 `set_cdp_chrome add <port> -AllowOrigins`(`--remote-allow-origins=*`)를 쓴다. Playwright/Puppeteer/Node/Python 은 Origin 헤더를 보내지 않으므로 필요 없다.
- **연결 종료 vs 브라우저 종료**: Playwright `browser.close()` / Puppeteer `browser.close()` 는 Chrome 을 끈다. 사용자가 계속 쓰는 창이면 Puppeteer 는 `disconnect()`, Playwright 는 프로세스 종료로 연결만 끊는다.

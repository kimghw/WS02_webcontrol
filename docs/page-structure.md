# e-Class 직원찾기(MemberList) 페이지 구조 — 확장으로 버튼 넣기 위한 조사

조사일 2026-09-28. KRS 전용 크롬(CDP 9333, 로그인 상태)에 붙어 실제 DOM을 읽어 정리했다.
조사 스크립트: `cdp-dump.mjs`(전체 HTML 저장), `cdp-inspect.mjs`(구조 요약 JSON).

## 1. URL / 확장 매칭

| 항목 | 값 |
|---|---|
| 페이지 | `https://eclass.krs.co.kr/eClassVer4/searchmember/MemberList` |
| 검색 파라미터 | `?searchOption=NAME|CODE|...&searchText=<검색어>` |
| 로그인 | 필요. 미로그인 시 `/eClassVer4/Account/Login?ReturnUrl=...` 으로 이동 |
| 매니페스트 matches | `https://eclass.krs.co.kr/eClassVer4/searchmember/MemberList*` (경로 대소문자가 섞여 쓰이므로 `https://eclass.krs.co.kr/*` 로 넓게 잡고 카드 존재 여부로 판단하는 방식이 더 안전) |
| 서버 | ASP.NET MVC (Razor scoped attr `b-…`), jQuery 3 + Bootstrap 4 + Font Awesome 6 |

## 2. 렌더링 방식

- 검색 결과는 **서버 렌더링**. 검색 버튼은 `window.location.href = "/eClassVer4/searchmember/MemberList?..."` 로 전체 페이지를 다시 연다. Ajax 로 결과를 갈아끼우지 않는다.
- 단, 페이지 안 "메인 / 파견·겸무" 토글이 `.person_main / .person_sub / .person_fc` 카드를 나중에 보이게 하므로 **MutationObserver 로 새 카드에도 붙이는 것이 안전**하다 (기존 확장도 그렇게 함).
- 부서명 클릭 = `openSearchDeptPage('<부서코드>')` → `?searchOption=CODE&searchText=<부서코드>` 로 이동 (부서 카드 + 부서원 카드 목록).
- AI 검색(JOBAI)은 별도 페이지 `/eClassVer4/SearchMember/AIMemberList?query=` 로 간다.

## 3. DOM 구조 (결과 영역)

```
div#content > div.main-content > div.page-content.container.container-plus > div.row
└─ div.item-list
   ├─ div.item                          ← 부서 카드 (person_main 없음)
   │  └─ div.profile-card
   │     ├─ div.search_info_dept_name h3.Korean   부서명
   │     └─ div.search_info_content#search_info_dept p   부서 메일
   └─ div.item.person_main              ← 직원 카드 (하나씩 반복)
      └─ div.profile-card.card ...
         ├─ div.image > img.profile-pic   src="/intra/intranet/member/pic/<userId>.gif"
         │                                onclick="copyToClipboard('<userId>')"  title="<userId>"
         ├─ div.search_info_main
         │  ├─ div.search_info_name > h3.Korean   이름 / h3.English 영문명
         │  └─ h4.search_info_position.Korean     직위
         ├─ div.search_info_sub
         │  ├─ #search_info_dept p.Korean.clickable  onclick="openSearchDeptPage('<부서코드>')"  부서명
         │  ├─ span.phone_number                     휴대폰(마스킹) / RunCall(...) 에 원번호
         │  └─ p (다음 칸)                            내선번호
         └─ div.search_info_btn          ← ★ 버튼 줄 (여기에 버튼을 append)
            ├─ button.btn.btn-outline-primary.mb-1   Ext    onclick="RunCall(this,'<내선>')"
            ├─ button.btn.btn-outline-orange.mb-1    Mobile
            ├─ button.btn.btn-outline-purple.mb-1    Task   onmouseover="titleMouseOver(event,this,'<userId>',…)"
            └─ a.btn.btn-outline-primary.mb-1.krs-teams-btn  Teams  ← 확장(meeting_room)이 넣은 것
```

## 4. 카드에서 값 꺼내는 자리 (셀렉터)

| 값 | 어디서 | 비고 |
|---|---|---|
| 버튼 넣을 줄 | `.search_info_btn` | 카드마다 1개 |
| 카드 루트 | `row.closest('.item')` | `.item.person_main` |
| 사용자 ID | `img.profile-pic` 의 src `/member/pic/<id>.gif`, `copyToClipboard('<id>')`, Task 의 `titleMouseOver(…,'<id>',…)` | `00000` 은 사진 없음 자리표시자 |
| 이메일 | `<id>@krs.co.kr` | 카드에 이메일 자체는 없음 |
| 이름 | `.search_info_name h3.Korean` | |
| 직위 | `h4.search_info_position.Korean` | |
| 부서코드 | `#search_info_dept p.clickable` 의 `openSearchDeptPage('<code>')` | 예: HER |
| 부서명 | `#search_info_dept p.Korean` 텍스트 | |
| 내선 | Ext 버튼 `RunCall(this,'<ext>')` | |

## 5. 이미 있는 확장 — 여기에 추가하는 것이 맞다

- **KRS WORKSPACE** (Manifest V3, 압축해제 로드) — 소스 `E:\dev\meeting_room`, 9333 KRS 프로필에 설치됨.
- `manifest.json` content_scripts: matches `https://eclass.krs.co.kr/*`, js `home.js`, `people.js`, run_at `document_idle`.
- `people.js`(루트) = 시동부. `.search_info_btn` 이 있으면 `import(chrome.runtime.getURL('src/people.js'))` 로 모듈을 불러 `startPeople(document)`.
- `src/people.js` = Teams 버튼 모듈. 패턴:
  - `ROW_SELECTOR='.search_info_btn'`, `BTN_CLASS='krs-teams-btn'`(중복 방지·제거용 표식)
  - `userIdOf(card)` / `nameOf(card)` / `emailOf(id)` 로 카드에서 값 추출
  - `buildButton()` 은 사이트 버튼과 같은 클래스(`btn btn-outline-* mb-1`) + FA6 아이콘
  - `mountTeams / unmountTeams`, `MutationObserver(body, subtree)` 로 나중에 뜨는 카드도 처리
  - `chrome.storage.local` 의 `teamsButton` 값으로 켜고 끔 (사이드패널 설정과 연동)
- 새 버튼(예: team)은 `src/people.js` 옆에 같은 얼개의 모듈을 하나 더 두고, 루트 `people.js` 에서 함께 시동하면 된다.

## 6. 조사 방법 (재현)

```
# KRS 전용 크롬(9333)이 떠 있고 MemberList 탭이 열려 있을 때
node cdp-dump.mjs "searchmember/MemberList" out.html
node cdp-inspect.mjs "searchmember/MemberList"
```
포트를 바꾸려면 `CDP_PORT=9444 node ...`.

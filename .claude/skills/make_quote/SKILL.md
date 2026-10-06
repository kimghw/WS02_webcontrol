---
name: make_quote
description: 장바구니 화면 캡처·주문서·공급자 견적서(이미지, 복사한 텍스트, HTML)에서 견적에 필요한 값만 뽑아 표준 견적서(Markdown 기본, xlsx/csv/json 선택)로 만든다. 무엇을 어떤 구조로 뽑을지는 스킬의 input.yaml 이 정하고(SSOT) 키마다 인라인 추출 프롬프트가 붙어 있어 그대로 따른다. "이 장바구니로 견적서 만들어", "캡처에서 품목·금액만 정리해", 네이버·쿠팡 등 쇼핑몰 장바구니 정리, 견적서 이미지를 표로, 여러 캡처를 한 견적으로 합치기, 견적 항목·키 추가/변경(input.yaml 수정) 요청 시 사용. 웹 페이지를 직접 열어 긁어오지는 않는다(로그인 장바구니·CDP 정탐은 별도 규약).
argument-hint: "[<이미지|텍스트|HTML 경로 ...>] [--out <파일> | --out-dir <폴더>] [--xlsx] [--csv] | schema | template | help"
---

# make_quote — 장바구니·견적서 원본 → 견적서

원본(장바구니 캡처, 주문서, 공급자 견적서)을 보고 **input.yaml 이 정한 키만** 뽑아 견적서를 만든다.
추출은 코드 에이전트가 한다: [input.yaml](input.yaml) 의 각 키에 붙은 `prompt`(인라인 추출 지시)대로 값을 읽어
같은 키 구조의 JSON 을 쓴다. 검증·기본값 채우기·렌더는 `scripts/make_quote.py` 가 한다(stdout JSON 1개).

**input.yaml 이 SSOT 다.** 견적서에 들어갈 항목을 바꾸고 싶으면(키 추가·삭제, 표시 이름, 추출 규칙, 정합성 검사,
표 열 순서) 이 스킬의 `input.yaml` 만 고친다(전역 스킬이면 `globalize sync`). 스크립트·SKILL.md 는 건드릴 필요 없다.

> 부작용: `render` 가 `--out`/`--out-dir` 로 파일을 쓴다(권장 `./quotes/<견적번호>.<ext>`). 기존 파일은 `--force`
> 없이는 덮어쓰지 않는다. 원본 캡처·추출 JSON 은 개인 구매 정보일 수 있으니 `quotes/` 는 커밋하지 않는다
> (배송지 상세·전화번호·계정명은 애초에 뽑지 않는다).

```
python "<이 SKILL.md 가 있는 폴더>/scripts/make_quote.py" <서브커맨드> [옵션]
```

| 서브커맨드 | 동작 |
|---|---|
| `schema` | input.yaml 의 키 트리(경로·type·required·default·label·prompt) + 전체 원칙·checks·render 를 JSON 으로 |
| `template` | 모든 키가 null 인 빈 JSON 골격(items 1행). 추출 결과를 이 모양으로 쓴다 |
| `validate --in <json> [--out-dir D]` | 미지 키·필수 누락·타입·enum·정합성(checks). 기본값(견적번호·견적일 등)을 채운 `data` 도 돌려준다 |
| `render --in <json> (--out F \| --out-dir D) [--format md,json,csv,xlsx] [--force]` | validate 후 견적서 생성. `--out` 은 파일 1개(확장자=형식), `--out-dir` 은 `<견적번호>.<ext>` 를 형식별 1개씩. 둘 다 없으면 `content` 로만 돌려준다(파일 안 씀). error 가 하나라도 있으면 렌더하지 않는다 |
| `help` | 도움말 |

공통 옵션 `--yaml F`: 다른 스키마 파일 사용(프로젝트 전용 항목이 필요하면 input.yaml 을 복사해 고친 뒤 지정).
`--in -` 는 stdin. 종료코드 0 정상 · 1 검증 error/거부 · 2 인자·파일 오류.

## 인자

| 인자 | 동작 |
|---|---|
| `help` / `-h` / `--help` | 이 인자 표와 서브커맨드 표만 출력하고 종료 |
| (없음) | 대화에 원본(첨부 이미지·붙여넣은 텍스트)이 있으면 그것으로 "절차" 진행. 없으면 원본을 달라고 한 줄로 요청 |
| `<경로 ...>` | 이미지(.png/.jpg)·텍스트(.txt/.md)·HTML(.html) 파일. 여러 개면 한 견적으로 합친다 |
| `--out <파일>` / `--out-dir <폴더>` | 출력 위치. 기본 `--out-dir quotes` |
| `--xlsx` / `--csv` | md·json 에 더해 그 형식도 생성(`--format md,json,xlsx` 로 전달) |
| `schema` / `template` | 스크립트 결과를 그대로 보여준다(파일 안 씀) |

## 절차

1. **원본 확보** — 이미지는 `Read` 로 연다(여러 장이면 전부). 텍스트·HTML 은 읽는다. **URL 만 주어졌으면** 페이지를 열어
   긁지 않는다(장바구니는 로그인 세션이 필요하고 웹 분석은 프로젝트의 CDP 정탐 규약을 따라야 한다). 캡처나 텍스트
   복사를 요청하고 종료한다.
2. **input.yaml 읽기 — 매번, 전체.** `<이 SKILL.md 가 있는 폴더>/input.yaml` 을 `Read` 로 읽는다. 기억이나 이 문서로
   대신하지 않는다(사용자가 키를 바꿨을 수 있다). 읽는 순서: `extraction.prompt`(전체 원칙) → `fields` 각 키의 `prompt`.
3. **추출 JSON 작성** — `template` 골격과 같은 키 구조로, 키마다 그 키의 `prompt` 대로 값을 넣는다.
   - 원본에 없으면 `null`. 만들어 넣지 않는다. 기본값이 있는 키(제목·견적번호·견적일·통화·수량·할인·배송비)는 원본에
     없으면 `null` 로 두면 스크립트가 채운다.
   - 금액은 숫자(`8800`). "8,800원" 같은 문자열도 스크립트가 바꾸지만 `normalized` 에 남으니 처음부터 숫자로.
   - 작업 메모는 `_source` 처럼 `_` 로 시작하는 키에(검증에서 무시).
   - 파일은 스크래치 또는 `quotes/draft_<slug>.json`. 작업용이지 산출물이 아니다.
4. **validate** — `errors` 가 있으면 JSON 을 고쳐 다시 돌린다(스키마 어긋남은 원본 탓이 아니라 추출 탓이다).
   `warnings` 중 `check:*` 는 원본을 **다시 보고** 판단한다: 읽기 실수면 값을 고치고, 원본 자체가 그 값이면(예: 화면
   합계와 항목 합이 다름) 그대로 두고 `meta.note` 에 "· 확인 필요: <무엇>" 을 적는다. `unknown_key` 는 오타이거나 스키마에
   없는 키다. 그 정보가 견적서에 꼭 필요하면 input.yaml 에 키를 추가한다("판단 규칙" 참고).
5. **render** — `render --in <draft> --out-dir quotes --format md,json` (xlsx/csv 요청 시 추가). `json` 을 같이 쓰는 이유:
   기본값이 채워진 확정본이라 나중에 다시 렌더해도 견적번호가 바뀌지 않는다(초안은 렌더할 때마다 `{seq}` 가 올라간다).
   사용자가 경로를 지정했으면 `--out`. `exists` 로 거부되면 사용자가 덮어쓰라고 한 경우에만 `--force`.
6. **보고** — 아래 형식. 견적서 본문을 되풀이해 출력하지 않는다(사용자가 파일을 열면 보인다). 품목이 3건 이하면 품목 표만
   붙여도 된다.

## 보고 형식

```
견적서: quotes/Q-20260930-01.md (+ .json[, .xlsx])
원본: 네이버 스토어 장바구니 캡처 1장 · 품목 1건 · 합계 11,300원(배송비 2,500원 포함)
검증: 통과 | 경고 N(어떤 검사)
비워둔 키: 수신·유효기간 (원본에 없음)
확인 필요: …                          (있을 때만)
```

## 판단 규칙

- **필요한 것만.** 견적서에 안 들어가는 정보(결제 배지·쿠폰 버튼·계정명·알림 수·추천 상품·상세주소·전화번호)는 JSON 어디에도
  넣지 않는다. "넣을까 말까" 는 그 키의 `prompt` 가 정한다. 어느 키의 prompt 에도 해당하지 않는 정보는 버린다.
- **추측 금지.** 잘려 보이는 값은 가장 그럴듯한 값 + note "확인 필요". 화면에 없는 합계를 계산해 넣었으면 note 에 "계산값".
- **탭·스토어가 여럿일 때.** 표시 중인 탭만 뽑고 다른 탭은 note 에 "N건 미포함". 스토어가 둘 이상이면 `meta.vendor` 는 null,
  `items[].vendor` 에 각각.
- **원본이 견적서일 때.** 공급가액/부가세 줄이 있으면 `tax_included=false`, `summary.vat` 를 채운다. 견적번호·유효기간은 원본 값.
- **스키마 변경 요청**("견적서에 납기 열 추가해줘") — input.yaml 의 해당 위치(`fields.items.item.fields` 등)에 키를 추가한다.
  `type`·`label`·`prompt`(어디서 어떻게 뽑고 무엇을 빼는지) 를 반드시 같이 쓰고, 표에 보이게 하려면 `render.item_columns`
  등에도 넣는다. prompt 는 `prompt: >-` 블록으로 쓴다(`: ` 가 들어가도 안전). 추가 후 `schema` 로 파싱을 확인한다.
- **하지 않는 것.** 웹 페이지 접속·로그인·CDP 정탐, 가격 비교·대안 추천, 실제 주문. 회사 서식(로고·직인)이 필요하면 xlsx 를
  낸 뒤 사용자가 서식으로 옮긴다.

## input.yaml 구조

```yaml
extraction:        # 전체 원칙 — 모든 키의 prompt 에 앞서 적용(보이는 값만, 선택 상품만, 표시 탭만, 배지·개인정보 제외 …)
fields:
  meta:            # 견적 정보: 제목·견적번호·견적일·유효기간·원본 종류·출처·원본 URL·캡처일·판매처·수신·배송지·통화·부가세 포함·비고
  items:           # 품목 리스트: 품명·옵션/규격·수량·단가·금액·판매처·링크·비고
  summary:         # 합계: 상품금액·할인·할인 내역·배송비·부가세·합계
checks:            # 정합성: 금액=수량×단가 · 상품금액=품목 합 · 합계 공식 · 부가세 플래그 (level: warn|error)
render:            # 머리 표 키 순서 · 품목 열 순서 · 합계 행 순서 · 통화 표기 · 꼬리말
```

키 속성: `type`(string·int·money·bool·date·url·enum·list·object) · `required` · `default`(`{today}`·`{date}`·`{seq}`) ·
`label` · `values` · **`prompt`** · `example` · `min`. null 뿐인 머리 행·품목 열은 렌더에서 자동 생략된다.

## 예시

- [assets/example_naver_cart.json](assets/example_naver_cart.json) — 네이버 스토어 장바구니 캡처(양말하우스 1건,
  배송비 2,500원, 지금배달 탭 1건 미포함) 추출 결과.
- [assets/example_naver_cart.md](assets/example_naver_cart.md) — 그 렌더 결과. 새 원본을 처리할 때 "이 정도 수준으로" 의 기준.

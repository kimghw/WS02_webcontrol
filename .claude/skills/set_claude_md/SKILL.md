---
name: set_claude_md
description: 웹 자동화(레시피 아키텍처) 프로젝트의 CLAUDE.md 를 표준 템플릿으로 생성하거나 기존 CLAUDE.md 에 누락된 상시 규약 절을 보강한다. 새 프로젝트 초기화, "CLAUDE.md 만들어/세팅해", 프로젝트 규약·상시 규약 넣기, 5계층(recipes·core·inputs·data·runners)·workflow.yaml SSOT·CDP 정탐·references/spec 문서 규약 적용, spec/·references/·probes/ 골격과 .gitignore 기본값 생성 요청 시 사용. 웹 자동화·스크래핑·브라우저 자동화 프로젝트를 새로 시작할 때 CLAUDE.md 가 없으면 먼저 이 스킬을 쓴다.
argument-hint: "(없음: 생성/보강) | <프로젝트 한 줄 설명> | check | scaffold | show | help"
---

# set_claude_md — 웹 자동화 프로젝트 CLAUDE.md 생성

현재 프로젝트 루트에 **레시피 아키텍처 상시 규약**을 담은 `CLAUDE.md` 를 만든다. 웹 자동화는 전부 이
구조(5계층 recipes·core·inputs·data·runners + 스킬 폴더 + workflow.yaml SSOT)로 가고, 웹 페이지 구조·
요청/응답 분석은 CDP 로 한다는 것이 규약의 핵심이다. 여기에 references(외부 지식)·spec(주제별 사양서)·
문서 갱신 검토 규약이 함께 들어간다.

**원본은 템플릿, CLAUDE.md 는 프로젝트 사본.** 규약 자체를 고치고 싶으면 이 스킬의
`assets/CLAUDE.template.md` 를 고친 뒤(전역 스킬이면 `globalize sync`) 각 프로젝트에서 `check`/`append` 로
따라잡는다. 프로젝트 고유 내용(업무 그룹 표·시스템별 채널 등)은 생성된 CLAUDE.md 에서 직접 편집한다.

모든 파일 작업은 `scripts/set_claude_md.py` 가 한다(stdout JSON 1개). 직접 파일을 쓰지 않는다.

```
python "<이 SKILL.md 가 있는 폴더>/scripts/set_claude_md.py" <서브커맨드> [옵션]
```

| 서브커맨드 | 동작 |
|---|---|
| `show` | 템플릿 원문 출력 |
| `check [--target CLAUDE.md]` | 템플릿 절(`# ` 헤더) 대비 보유/누락/추가 절 목록 |
| `render --name N [--desc D] [--out F] [--force]` | 새 CLAUDE.md 생성. 존재 시 실패, `--force` 는 `.bak` 백업 후 덮어쓰기 |
| `append [--target F] [--name N] [--desc D]` | 누락 절만 파일 끝에 추가(기존 내용 불변) |
| `scaffold [--root .]` | `spec/`·`references/`·`probes/out/`(+.gitkeep), `.gitignore` 기본 항목, `spec/spec_아키텍처.md` ①~④ 뼈대. 기존 파일은 절대 덮어쓰지 않음 |

## 인자

| 인자 | 동작 |
|---|---|
| `help` / `-h` / `--help` | 이 인자 표와 서브커맨드 표만 출력하고 종료 |
| (없음) | 아래 "절차" — CLAUDE.md 가 없으면 생성, 있으면 누락 절 보강 |
| `<프로젝트 한 줄 설명>` | 위와 같되 그 문장을 제목 아래 첫 문장(`{{PROJECT_DESC}}`)으로 사용 |
| `check` | 읽기 전용 — 현재 CLAUDE.md 의 누락 절만 보고 |
| `scaffold` | CLAUDE.md 생성/보강 + 폴더·.gitignore·spec_아키텍처 골격까지 |
| `show` | 템플릿 원문만 출력 |

인자는 조합 가능(`scaffold KRS 업무 자동화 프로젝트` = scaffold + 설명문). `check`·`show`·`help` 는
파일을 바꾸지 않는다.

## 절차

1. **프로젝트명·설명 확정**
   - 프로젝트명 = 현재 작업 디렉터리의 폴더명. 사용자가 다른 이름을 말했으면 그것.
   - 한 줄 설명 = 인자로 준 문장 > 대화에서 사용자가 말한 프로젝트 목적 > 기존 `README*`·`CLAUDE.md`
     첫 문단에서 추출. 셋 다 없으면 **묻지 말고** 플레이스홀더로 두고 보고에서 알린다(설명은 사용자가
     한 줄 고치면 끝나는 값이라 대기시킬 이유가 없다).
2. **기존 CLAUDE.md 확인** — `check` 실행.
   - 없음(`exists: false`) → 3 으로.
   - 있음 → `missing` 이 비어 있으면 "이미 표준 절을 모두 보유" 로 보고하고 종료(scaffold 요청이면 5 로).
     `missing` 이 있으면 **append 가 기본**이다: 사용자가 쓴 프로젝트 고유 규약을 지우지 않기 위해
     덮어쓰기는 사용자가 명시적으로 "덮어써/새로 만들어" 라고 했을 때만 `render --force` 로 한다
     (`.bak` 이 남는다). 어느 쪽인지 대화로 판단할 수 없고 세션이 대화형이면 한 번 묻고, 비대화형이면 append.
3. **생성** — `render --name <프로젝트명> --desc "<설명>"`.
4. **보강** — `append --name <프로젝트명> --desc "<설명>"`. 추가된 절은 파일 끝에 붙으므로 사용자에게
   "끝에 붙었다, 순서 조정은 자유" 라고 알린다.
5. **골격(scaffold 인자일 때만)** — `scaffold`. 결과의 `created`·`skipped_existing` 을 그대로 보고.
   `.gitignore` 는 누락 줄만 덧붙이고, `spec_아키텍처.md` 는 없을 때만 만든다.
6. **보고** — 아래 형식. 이어서 사용자가 채워야 할 곳을 짚는다: 업무 그룹 표의 플레이스홀더 행,
   한 줄 설명(플레이스홀더로 남았을 때), `spec_아키텍처.md` ② 채널 표.

## 보고 형식

```
CLAUDE.md: 생성 | 보강(+N절: …) | 변경 없음(표준 절 모두 보유)
백업: CLAUDE.md.bak (덮어쓴 경우만)
골격: created … / skipped …          (scaffold 일 때만)
채울 곳: 업무 그룹 표 1행 · 한 줄 설명 · spec_아키텍처 ② 채널 표
```

한 줄씩만. 생성된 문서 본문을 되풀이해 출력하지 않는다(사용자가 파일을 열면 보인다).

## 판단 규칙

- **템플릿을 프로젝트에서 임의로 다듬지 않는다.** 생성 직후 "이 프로젝트엔 이 절이 안 맞아 보인다" 는
  생각이 들어도 절을 빼거나 문구를 바꾸지 않고 그대로 두고 보고에서 언급만 한다. 규약 변경은 템플릿
  (원본)에서 하는 것이 원칙이고, 그 판단은 사용자 몫이다.
- **절 비교는 `# ` 헤더 키(` — `·` (` 앞부분)로 한다.** 사용자가 헤더 뒤 설명을 바꿔도(`# 보안 기본값
  (…)`) 같은 절로 인식한다. 헤더 자체를 개명했으면 중복이 생길 수 있으니 `check` 의 `extra_in_target`
  을 보고 사용자에게 알린다.
- 이미 다른 구조(예: 일반 웹앱)의 CLAUDE.md 가 충실히 있는 프로젝트에 이 스킬을 쓰라는 요청이면, append
  가 그 문서의 성격을 바꿀 수 있음을 한 문장으로 짚고 진행한다(사용자가 요청한 것이므로 막지 않는다).
- CLAUDE.md 를 만든 뒤 업무 그룹 폴더(`<코드>_<대표업무>/` 5계층)까지 만들어 달라는 요청은 이 스킬 범위
  밖이다 — 규약대로 만들되 근거는 [references/recipe_architecture.md](references/recipe_architecture.md)
  (원형 프로젝트 실물·workflow 뼈대·probe 패턴)를 읽고 진행한다.

## 템플릿이 담는 절 (assets/CLAUDE.template.md)

1. `<프로젝트명> — 상시 규약` — 문서 범위·용어(업무 그룹·working unit·그룹 폴더 규약)
2. 일반 원칙 — 사전 작성→검증→주입→저장까지만, 러너는 YAML 만 소비, dry-run 기본, 변경은 한 곳만
3. 업무 그룹 — 그룹 표(플레이스홀더 1행)
4. 업무절차 2계통 — ① 생명주기(create/update/retire) ② 실건 실행
5. 웹 자동화 표준 아키텍처 — 4대 구성, **5계층 표(recipes·core·inputs·data·runners)**, 스킬 폴더,
   workflow.yaml SSOT, primary/helper 경계, 구조 검증
6. **웹 분석·정탐은 CDP 로** — 채널(포트+프로필), 분석 대상↔CDP 도메인, probes/, 정탐 결과 귀속
7. 보안 기본값 — inputs/data/logs/프로필 gitignore, `.env.*` SSOT
8. 로그·감독 계약(요약) — steps.jsonl/final.json, verdict, 채널 락, 판정 2단
9. 지식저장소 `<cwd>/references`
10. 문서 갱신 검토(서브에이전트)
11. 요구사항·질의 관리 — `<cwd>/spec` 주제별 사양서(①~④)

9~11 은 사용자가 준 원문을 그대로 실었다(11 의 "작성 주체" 만 검토 의견대로 "사용자 또는 코드
에이전트" 로 일반화).

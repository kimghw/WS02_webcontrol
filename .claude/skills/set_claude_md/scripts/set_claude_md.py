#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""set_claude_md.py — 웹 자동화(레시피 아키텍처) 프로젝트의 CLAUDE.md 생성·보강 도구 (set_claude_md 스킬 실행체)

템플릿 `assets/CLAUDE.template.md` 의 `{{PROJECT_NAME}}`·`{{PROJECT_DESC}}` 를 치환해 CLAUDE.md 를 만들고,
기존 CLAUDE.md 가 있으면 최상위 절(`# ` 헤더)을 비교해 누락된 절만 끝에 덧붙인다. 표준 폴더 골격
(spec/·references/·probes/out/)과 .gitignore 기본 항목, spec_아키텍처.md 뼈대도 만들 수 있다.
검색 키워드: CLAUDE.md 생성, 상시 규약, 누락 절, scaffold, 레시피 아키텍처.

서브커맨드 (출력은 항상 stdout JSON 1개):
  show                                   템플릿 원문을 stdout 에 그대로 출력(JSON 아님)
  check    [--target CLAUDE.md]          템플릿 절 대비 대상 파일의 보유/누락 절 목록
  render   --name N [--desc D] [--out CLAUDE.md] [--force]
                                         새 CLAUDE.md 생성. 이미 있으면 실패, --force 면 .bak 백업 후 덮어쓰기
  append   [--target CLAUDE.md] [--name N] [--desc D]
                                         누락된 절만 대상 파일 끝에 추가(기존 내용은 건드리지 않음)
  scaffold [--root .]                    spec/ references/ probes/out/ (+.gitkeep), .gitignore 기본 항목,
                                         spec/spec_아키텍처.md ①~④ 뼈대. 기존 파일은 절대 덮어쓰지 않음

절 비교 키: `# ` 헤더 텍스트에서 ` — ` 또는 ` (` 앞부분(공백 정규화). 템플릿 첫 절(제목)은 비교 대상에서 제외.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

try:  # Windows 콘솔(cp949) 에서도 한글 JSON 이 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_DIR / "assets" / "CLAUDE.template.md"
PLACEHOLDER_NAME = "{{PROJECT_NAME}}"
PLACEHOLDER_DESC = "{{PROJECT_DESC}}"
DESC_FALLBACK = "<프로젝트 한 줄 설명>."

GITIGNORE_LINES = [
    "# 보안 기본값(CLAUDE.md) — 실값·로그·캡처는 커밋하지 않는다. 커밋은 빈 양식·비식별 fixture·코드·문서만.",
    "*_inputs/*",
    "!*_inputs/.gitkeep",
    "*_data/*",
    "!*_data/.gitkeep",
    "logs/",
    "probes/out/",
    "captures/",
    "*.png",
    "chrome_profile/",
    "chrome_binding.yaml",
    ".env*",
    "!.env*.example",
    "__pycache__/",
    "*.pyc",
    ".venv/",
]

SPEC_ARCH_SKELETON = """# spec_아키텍처 — {name} 프로젝트 구조·이행

상시 규약은 [CLAUDE.md](../CLAUDE.md)에 있고, 이 문서는 그 규약의 **근거·결정 이력·이행 상태**의 원본이다
(원본-링크 원칙 — 같은 사실을 두 곳에 쓰지 않는다).

## ① 질의·요청 히스토리

- {today}: 프로젝트 초기화 — set_claude_md 스킬로 CLAUDE.md(상시 규약)와 spec/·references/·probes/ 골격 생성.

## ② 확정 사양

### 2.0 업무 그룹 구성·분리 사유

(그룹을 추가할 때 여기에 "왜 별도 그룹인가"를 적고 CLAUDE.md 업무 그룹 표에는 행만 추가한다.)

### 2.1 크롬 채널(포트·프로필) 구성

| 채널 | 포트 | 프로필 | 대상 시스템(SSO 경계) |
|---|---|---|---|
| | | | |

### 2.2 디렉토리 구조

(5계층·스킬 폴더·공용 계층의 실제 배치. 규약 자체는 CLAUDE.md, 여기는 이 프로젝트의 실물.)

## ③ 구현 상태

- (그룹별 이행 상태)

## ④ 미결/후속

- (정탐만 진행 중인 그룹, 미착수 항목)
"""


# ── 파일 IO ────────────────────────────────────────────────────────────────────
def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return code


# ── 절 파싱 ────────────────────────────────────────────────────────────────────
def split_sections(text: str) -> list[dict]:
    """최상위 `# ` 헤더 단위로 분할. 코드펜스 안의 `# ` 는 무시. 첫 헤더 앞 텍스트는 preamble."""
    sections: list[dict] = []
    cur = {"header": None, "key": None, "lines": []}
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("# "):
            sections.append(cur)
            header = line[2:].strip()
            cur = {"header": header, "key": section_key(header), "lines": []}
        cur["lines"].append(line)
    sections.append(cur)
    return sections


# 같은 절인데 헤더 표기가 다른 알려진 경우(원형 프로젝트 krs-web-agents 등) — 값이 정규 키
SECTION_ALIASES = {
    "자동화 표준 아키텍처": "웹 자동화 표준 아키텍처",
    "웹 분석은 CDP 로": "웹 분석·정탐은 CDP 로",
    "웹 분석·정탐은 CDP로": "웹 분석·정탐은 CDP 로",
}


def section_key(header: str) -> str:
    key = re.split(r"\s+—\s+|\s+\(", header, maxsplit=1)[0]
    key = re.sub(r"\s+", " ", key).strip()
    return SECTION_ALIASES.get(key, key)


def body_sections(sections: list[dict]) -> list[dict]:
    return [s for s in sections if s["header"] is not None]


def render_template(name: str, desc: str | None) -> tuple[str, list[str]]:
    text = read_text(TEMPLATE)
    desc = (desc or "").strip()
    if desc and not desc.endswith((".", "。", "다", "다.")):
        desc = desc + "."
    if not desc:
        desc = DESC_FALLBACK
    text = text.replace(PLACEHOLDER_NAME, name).replace(PLACEHOLDER_DESC, desc)
    left = [p for p in (PLACEHOLDER_NAME, PLACEHOLDER_DESC, "<프로젝트 한 줄 설명>", "`<코드>`") if p in text]
    return text, left


def compare(target_text: str, template_text: str) -> dict:
    tmpl = body_sections(split_sections(template_text))[1:]  # 첫 절(제목)은 제외
    have = {s["key"]: s["header"] for s in body_sections(split_sections(target_text))}
    present, missing = [], []
    for s in tmpl:
        (present if s["key"] in have else missing).append(s["header"])
    extra = [h for k, h in have.items() if k not in {s["key"] for s in tmpl}]
    return {"present": present, "missing": missing, "extra_in_target": extra}


# ── 서브커맨드 ─────────────────────────────────────────────────────────────────
def cmd_show(_: argparse.Namespace) -> int:
    sys.stdout.write(read_text(TEMPLATE))
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    target = Path(a.target)
    if not target.exists():
        return emit({"ok": False, "target": str(target), "exists": False,
                     "hint": "render 로 새로 생성"}, 1)
    res = compare(read_text(target), read_text(TEMPLATE))
    res.update({"ok": True, "target": str(target), "exists": True,
                "missing_count": len(res["missing"])})
    return emit(res)


def cmd_render(a: argparse.Namespace) -> int:
    out = Path(a.out)
    backup = None
    if out.exists():
        if not a.force:
            return emit({"ok": False, "out": str(out), "reason": "exists",
                         "hint": "append 로 누락 절만 추가하거나 --force(백업 후 덮어쓰기)"}, 1)
        backup = out.with_suffix(out.suffix + ".bak")
        shutil.copyfile(out, backup)
    text, left = render_template(a.name, a.desc)
    write_text(out, text)
    headers = [s["header"] for s in body_sections(split_sections(text))]
    return emit({"ok": True, "out": str(out), "backup": str(backup) if backup else None,
                 "sections": headers, "placeholders_left": left})


def cmd_append(a: argparse.Namespace) -> int:
    target = Path(a.target)
    if not target.exists():
        return emit({"ok": False, "target": str(target), "reason": "missing",
                     "hint": "render 로 새로 생성"}, 1)
    cur = read_text(target)
    name = a.name or target.resolve().parent.name
    tmpl_text, _ = render_template(name, a.desc)
    tmpl_sections = body_sections(split_sections(tmpl_text))[1:]
    have = {s["key"] for s in body_sections(split_sections(cur))}
    to_add = [s for s in tmpl_sections if s["key"] not in have]
    if not to_add:
        return emit({"ok": True, "target": str(target), "added": [], "note": "누락 절 없음 — 변경 없음"})
    blocks = ["\n".join(s["lines"]).rstrip() for s in to_add]
    new_text = cur.rstrip("\n") + "\n\n" + "\n\n".join(blocks) + "\n"
    write_text(target, new_text)
    return emit({"ok": True, "target": str(target), "added": [s["header"] for s in to_add]})


def cmd_scaffold(a: argparse.Namespace) -> int:
    root = Path(a.root).resolve()
    created, skipped = [], []

    def touch(rel: str) -> None:
        p = root / rel
        if p.exists():
            skipped.append(rel)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        created.append(rel)

    for rel in ("spec/.gitkeep", "references/.gitkeep", "probes/out/.gitkeep"):
        touch(rel)

    gi = root / ".gitignore"
    existing = read_text(gi).splitlines() if gi.exists() else []
    have = {ln.strip() for ln in existing}
    add = [ln for ln in GITIGNORE_LINES if ln.strip() not in have and not (ln.startswith("#") and existing)]
    if add:
        text = ("\n".join(existing).rstrip("\n") + "\n\n" if existing else "") + "\n".join(add) + "\n"
        write_text(gi, text)
        created.append(f".gitignore (+{len(add)} lines)")
    else:
        skipped.append(".gitignore")

    spec_arch = root / "spec" / "spec_아키텍처.md"
    if spec_arch.exists():
        skipped.append("spec/spec_아키텍처.md")
    else:
        write_text(spec_arch, SPEC_ARCH_SKELETON.format(name=root.name, today=date.today().isoformat()))
        created.append("spec/spec_아키텍처.md")

    return emit({"ok": True, "root": str(root), "created": created, "skipped_existing": skipped})


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="웹 자동화 프로젝트 CLAUDE.md 생성·보강 (set_claude_md 스킬)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="템플릿 원문 출력").set_defaults(fn=cmd_show)

    p = sub.add_parser("check", help="템플릿 절 대비 누락 절 확인")
    p.add_argument("--target", default="CLAUDE.md")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("render", help="새 CLAUDE.md 생성")
    p.add_argument("--name", required=True, help="프로젝트명(제목)")
    p.add_argument("--desc", default="", help="프로젝트 한 줄 설명(없으면 플레이스홀더)")
    p.add_argument("--out", default="CLAUDE.md")
    p.add_argument("--force", action="store_true", help="존재 시 .bak 백업 후 덮어쓰기")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("append", help="누락 절만 기존 CLAUDE.md 끝에 추가")
    p.add_argument("--target", default="CLAUDE.md")
    p.add_argument("--name", default=None, help="치환용 프로젝트명(기본: 대상 파일의 폴더명)")
    p.add_argument("--desc", default="")
    p.set_defaults(fn=cmd_append)

    p = sub.add_parser("scaffold", help="spec/ references/ probes/out/ .gitignore spec_아키텍처.md 골격")
    p.add_argument("--root", default=".")
    p.set_defaults(fn=cmd_scaffold)
    return ap


def main() -> int:
    if not TEMPLATE.exists():
        return emit({"ok": False, "reason": f"template missing: {TEMPLATE}"}, 2)
    a = build_parser().parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

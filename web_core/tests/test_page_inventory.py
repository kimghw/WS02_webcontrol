"""web_core 순수 로직 테스트 — 브라우저 없이 포트 결정·범용 fieldmap 초안·초안 요약·인벤토리 diff·POST 요약·실연 시퀀스를 검증.

실행: python web_core/tests/test_page_inventory.py   (unittest, exit 0 = 통과)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_core import cdp_channel as ch  # noqa: E402
from web_core import page_inventory as inv  # noqa: E402
from web_core import probe_kit as kit  # noqa: E402


def _f(id_, tag="input", type_="text", label="", **kw):
    d = {"tag": tag, "type": type_, "id": id_, "name": id_, "visible": True, "label": label}
    d.update(kw)
    return d


def generic_inventory() -> dict:
    """ASP.NET 이 아닌 일반 사이트 폼(접두 없음, id 에 ':' 포함 컨트롤 하나)."""
    fields = [
        _f("userName", label="이름"),
        _f("amount", type_="number", label="금액", maxlength=12),
        _f("category", tag="select", type_="select-one", label="분류",
           options=[{"v": "", "t": "선택"}, {"v": "a", "t": "출장"}]),
        _f("memo", tag="textarea", type_="textarea", label="메모"),
        _f("form:agree", type_="checkbox", label="동의"),
        _f("btnSave", tag="button", type_="submit", text="저장"),
    ]
    return {"ts": "20261006_000000", "url": "https://example.test/apply", "frames": [
        {"index": 0, "url": "https://example.test/apply", "fields": fields, "anchors": [],
         "editors": {"contenteditable": 1}},
    ]}


class ChannelTests(unittest.TestCase):
    def test_resolve_port(self):
        os.environ.pop("WC_TEST_PORT", None)
        self.assertIsNone(ch.resolve_port(None, "WC_TEST_PORT"))           # 범용: 기본값 없으면 추측하지 않음
        self.assertEqual(ch.resolve_port(None, "WC_TEST_PORT", 9555), 9555)
        self.assertEqual(ch.resolve_port("9222", "WC_TEST_PORT", 9555), 9222)
        os.environ["WC_TEST_PORT"] = "9444"
        try:
            self.assertEqual(ch.resolve_port(None, "WC_TEST_PORT", 9555), 9444)
        finally:
            os.environ.pop("WC_TEST_PORT", None)

    def test_dead_port(self):
        self.assertIsNone(ch.channel_info(1))


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.inv = generic_inventory()
        self.text = inv.fieldmap_draft(self.inv, source="inventory.json")

    def test_generic_draft(self):
        t = self.text
        self.assertIn('prefix: ""', t)
        self.assertIn('anchor: "#userName"   # 후보', t)
        self.assertIn('selector: "#userName"', t)
        self.assertIn("maxlength: 12", t)
        self.assertIn('options: ["선택", "출장"]', t)
        self.assertIn('note: "textarea"', t)
        self.assertIn('url: "https://example.test/apply"', t)
        self.assertIn('{id: "btnSave", text: "저장"', t)
        self.assertIn("contenteditable: 1", t)
        self.assertIn("TODO — 저장 후 확인할 조건", t)
        self.assertIn("probes/web_probe.py", t)
        self.assertNotIn("fields.title", t)

    def test_css_id_and_hooks(self):
        self.assertEqual(inv.css_id("a_b-1"), "#a_b-1")
        self.assertEqual(inv.css_id("form:agree"), '[id="form:agree"]')
        # 꼬리 번호 없는 checkbox 는 DSL v1 밖 → hooks_후보
        self.assertIn('{id: "form:agree", tag: input, type: "checkbox"', self.text)

    def test_summary(self):
        s = inv.draft_summary(self.text)
        self.assertEqual(s["text"], 3)        # userName·amount·memo
        self.assertEqual(s["select"], 1)
        self.assertEqual(s["hooks"], 1)
        self.assertTrue(s["widgets"])

    def test_empty(self):
        t = inv.fieldmap_draft({"frames": []})
        self.assertIn("편집 가능 컨트롤을 찾지 못함", t)
        self.assertIn("anchor: TODO", t)
        self.assertFalse(inv.draft_summary(t)["widgets"])

    def test_extension_points(self):
        t = inv.fieldmap_draft(self.inv, anchor="#userName", title_id="userName",
                               open_lines=["open:", '  url: "X"'], extra_lines=["", "toolbar: {}"])
        self.assertIn("  title:\n    primitive: text", t)
        self.assertIn('fields.title 비어있지 않음', t)
        self.assertIn('  url: "X"', t)
        self.assertNotIn("example.test/apply\"   # 실측", t)
        self.assertIn("toolbar: {}", t)


class DiffTests(unittest.TestCase):
    def test_diff(self):
        before = generic_inventory()
        after = generic_inventory()
        after["frames"][0]["fields"] = after["frames"][0]["fields"][1:] + [_f("row_ctl02_qty", label="수량")]
        d = inv.inventory_diff(before, after)
        self.assertEqual([x["id"] for x in d["added"]], ["row_ctl02_qty"])
        self.assertEqual([x["id"] for x in d["removed"]], ["userName"])


class KitTests(unittest.TestCase):
    def test_summarize_post(self):
        body = "__EVENTTARGET=ctl00%24Save&__EVENTARGUMENT=&__VIEWSTATE=xxx&txtName=%ED%99%8D&amt=100"
        s = kit.summarize_post(body, "application/x-www-form-urlencoded")
        self.assertEqual(s["__EVENTTARGET"], "ctl00$Save")
        self.assertIn("txtName", s["keys"])
        self.assertNotIn("__VIEWSTATE", s["keys"])
        self.assertNotIn("raw", s)                       # 기본: 값 마스킹
        self.assertEqual(kit.summarize_post('{"a":1,"b":2}', "application/json")["json_keys"], ["a", "b"])
        self.assertIn("raw", kit.summarize_post(body, "", values=True))
        self.assertIsNone(kit.summarize_post("", ""))

    def test_load_env(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env.test"
            p.write_text("# c\nWC_T1=abc\nWC_T2 = 'x y'\nbad\n", encoding="utf-8")
            os.environ.pop("WC_T1", None)
            os.environ.pop("WC_T2", None)
            try:
                self.assertEqual(kit.load_env(p), ["WC_T1", "WC_T2"])
                self.assertEqual(os.environ["WC_T2"], "x y")
            finally:
                os.environ.pop("WC_T1", None)
                os.environ.pop("WC_T2", None)

    def test_recorder_actions(self):
        rec = kit.Recorder(ctx=None)
        rec._push({"kind": "navigate", "main": True, "url": "https://x/a"})
        rec._push({"kind": "navigate", "main": False, "url": "about:blank"})       # 빈 서브프레임 제외
        rec._push({"kind": "click", "page": 0, "frame": "", "target": {"selector": "#name", "tag": "input"}})
        rec._push({"kind": "click", "page": 0, "frame": "", "target": {"selector": "#name", "tag": "input"}})  # 연속 중복
        rec._push({"kind": "change", "page": 0, "frame": "", "target": {"selector": "#name", "tag": "input", "value_len": 3}})
        rec._push({"kind": "dialog", "page": 0, "message": "저장하시겠습니까?"})
        acts = rec.actions()
        self.assertEqual([a["kind"] for a in acts], ["navigate", "click", "change", "dialog"])
        self.assertEqual(acts[2]["value_len"], 3)
        self.assertNotIn("value", acts[2])


if __name__ == "__main__":
    unittest.main(verbosity=1)

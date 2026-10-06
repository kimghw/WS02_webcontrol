"""ea_core 순수 로직 테스트 — 브라우저 없이 세션 판정·진입 URL·카탈로그 파싱·eclass fieldmap 초안 어댑터를 검증.

실행: python ea_approval/ea_core/tests/test_inventory.py   (unittest, exit 0 = 통과)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

EA_DIR = Path(__file__).resolve().parents[2]
ROOT = EA_DIR.parent
for _p in (ROOT, EA_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from ea_core import eclass_inventory as inv  # noqa: E402
from ea_core import eclass_session as es  # noqa: E402

P = "ctl00_ContentPlaceHolder_Content_"


def _f(id_, tag="input", type_="text", label="", **kw):
    d = {"tag": tag, "type": type_, "id": id_, "name": id_.replace("_", "$"), "visible": True, "label": label}
    d.update(kw)
    return d


def fixture_inventory() -> dict:
    """probes/fixtures/eclass_form_fixture.html 과 같은 구조의 합성 인벤토리."""
    form_fields = [
        _f("ctl00_ApplineInfoInReportKRTA1_txtDocTitle", label="제목"),
        _f(P + "GuMeDeSang_0", type_="checkbox", label="PC류"),
        _f(P + "GuMeDeSang_1", type_="checkbox", label="자산"),
        _f(P + "GuMeDeSang_2", type_="checkbox", label="용역"),
        _f(P + "SaUpNeYong", tag="textarea", type_="textarea", label="사업내용"),
        _f(P + "ddlYesanType", tag="select", type_="select-one", label="예산유형",
           options=[{"v": "", "t": "선택"}, {"v": "1", "t": "일반사업"}, {"v": "2", "t": "국가수탁과제"}]),
        _f(P + "dtpEDate_dateInput", label="납품요청일"),
        _f(P + "NapumPlace", label="납품장소", maxlength=100),
        _f(P + "rblUrgent_0", type_="radio", label="예"),
        _f(P + "rblUrgent_1", type_="radio", label="아니오"),
        _f(P + "fuAttach", type_="file", label="첨부"),
        _f(P + "rptRequet_ctl01_txtItemName", label="품명"),
        _f(P + "rptRequet_ctl01_txtCnt", label="수량"),
        _f(P + "rptRequet_ctl01_txtEstimate", label="예상금액"),
        {"tag": "input", "type": "hidden", "id": None, "name": "hf", "visible": False, "hidden": True},
    ]
    anchors = [{"id": P + "LinkButton1", "text": "행추가",
                "href": "javascript:__doPostBack('ctl00$ContentPlaceHolder_Content$LinkButton1','')",
                "onclick": None, "visible": True}]
    toolbar = {"index": 1, "name": "toolbar", "url": "about:srcdoc",
               "fields": [_f("btnSave", type_="button", text="저장", title="입력한 내용을 저장합니다."),
                          _f("btnApproval", type_="button", text="상신")],
               "anchors": []}
    form = {"index": 2, "name": "REA_form", "url": "about:srcdoc", "fields": form_fields, "anchors": anchors,
            "editors": {"dext_body": True}}
    return {"form_id": "KR_Fixture", "ts": "20260930_000000", "frames": [{"index": 0, "url": "file:///x", "fields": []}, toolbar, form]}


class SessionTests(unittest.TestCase):
    def test_classify_url(self):
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/eClassVer4/Account/Login?ReturnUrl=x"), es.NEEDS_LOGIN)
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/RealEANET/loginbyname.aspx?ReturnUrl=x"), es.NEEDS_NAME)
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/RealEANET/ErrorPages/MsgBox.aspx?caption=x"), es.REJECTED)
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/RealEANet/Main/DocumentView.aspx?FORMID=A"), es.OK)
        self.assertEqual(es.classify_url("https://gate.krs.co.kr/"), es.NEEDS_LOGIN)
        self.assertEqual(es.classify_url("file:///C:/x.html"), es.NOT_ECLASS)
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/x", "PC 인증이 필요합니다"), es.NEEDS_DEVICE_AUTH)
        self.assertEqual(es.classify_url("https://eclass.krs.co.kr/x", "OTP 번호를 입력"), es.NEEDS_OTP)

    def test_tab_kind_and_hint(self):
        tabs = es.tab_summary([{"url": es.EAPPROVAL_URL, "title": "e-Class"},
                               {"url": "https://outlook.cloud.microsoft/", "title": "mail"}])
        self.assertEqual([t["kind"] for t in tabs], ["eapproval", "other"])
        self.assertEqual(es.session_hint(tabs), "eapproval_open")
        self.assertEqual(es.session_hint(es.tab_summary([{"url": es.LOGIN_URL}])), es.NEEDS_LOGIN)
        self.assertEqual(es.session_hint([]), "no_eclass_tab")
        self.assertEqual(es.tab_kind("https://eclass.krs.co.kr/RealEANet/Main/DocumentView.aspx?FORMID=X"), "docview")
        # ReturnUrl 에 DocumentView/MainFrameTA 가 인코딩돼 있어도 로그인 계열로 분류(샌드박스 실측 2026-09-30)
        self.assertEqual(es.tab_kind(es.build_entry_url("KR_X")), "loginbyname")
        self.assertEqual(es.tab_kind("https://eclass.krs.co.kr/eClassVer4/Account/Login?ReturnUrl=%2FeClassVer4%2FCommon%2F"
                                     "Default%3Ftitle%3De-Approval%26menu%3D%252FRealEANet%252FMain%252FMainFrameTA.aspx"), "login")

    def test_entry_url(self):
        u = es.build_entry_url("KR_EA_Form2_Test")
        self.assertTrue(u.startswith(es.LOGINBYNAME_URL + "?ReturnUrl="))
        self.assertIn("FORMID%3DKR_EA_Form2_Test", u)
        self.assertNotIn("&FORMID", u)   # ReturnUrl 안의 & 는 인코딩되어야 한다
        self.assertEqual(es.form_id_from_url(es.build_document_url("KR_X")), "KR_X")

    def test_resolve_port(self):
        import os
        os.environ.pop(es.CHANNEL_ENV_PORT, None)
        self.assertEqual(es.resolve_port(None), es.CHANNEL_DEFAULT_PORT)
        self.assertEqual(es.resolve_port("9222"), 9222)
        os.environ[es.CHANNEL_ENV_PORT] = "9444"
        try:
            self.assertEqual(es.resolve_port(None), 9444)
        finally:
            os.environ.pop(es.CHANNEL_ENV_PORT, None)


class CatalogTests(unittest.TestCase):
    def test_parse_and_dedupe(self):
        oc = ("javascript:return OpenAppDocWin('/RealEANET/Main/DocumentView.aspx?FORMID=KR_EA_Form2"
              "&DOCID=&GROUPID=0&MDTID=0&DID=0&ISMODIFY=0', 1024, 768);")
        p = inv.parse_open_app_doc_win(oc)
        self.assertEqual(p["form_id"], "KR_EA_Form2")
        self.assertTrue(p["url"].startswith("/RealEANET/Main/DocumentView.aspx?FORMID=KR_EA_Form2"))
        forms = inv.dedupe_forms([
            {"label": "", "onclick": oc, "visible": True},           # 아이콘 앵커(라벨 없음)는 JS 에서 이미 제외되지만 방어
            {"label": "기안문", "onclick": oc, "visible": False},
            {"label": "기안문", "onclick": oc, "visible": True},
            {"label": "없음", "onclick": "javascript:void(0)", "visible": True},
        ])
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]["form_id"], "KR_EA_Form2")
        self.assertTrue(forms[0]["visible"])

    def test_assign_categories(self):
        tabs = [{"id": "t0", "text": "기안문"}, {"id": "t1", "text": "양식결재"}]
        forms = [{"form_id": "A", "container": "c133"}, {"form_id": "B", "container": "c134"},
                 {"form_id": "C", "container": "c134"}]
        out = inv.assign_categories(forms, tabs)
        self.assertEqual([f["category"] for f in out], ["기안문", "양식결재", "양식결재"])
        out2 = inv.assign_categories([{"form_id": "A", "container": "c1"}], tabs)   # 개수 불일치 → None
        self.assertIsNone(out2[0]["category"])


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.inv = fixture_inventory()
        self.text = inv.fieldmap_draft(self.inv, "KR_Fixture", "inventory.json")

    def test_pick_frame_and_prefix(self):
        fr = inv.pick_form_frame(self.inv["frames"])
        self.assertEqual(fr["name"], "REA_form")
        ids = [f["id"] for f in fr["fields"] if f.get("id")]
        self.assertEqual(inv.detect_prefix(ids), P)

    def test_primitives(self):
        t = self.text
        self.assertIn('prefix: "#' + P + '"', t)
        self.assertIn('selector: "#ctl00_ApplineInfoInReportKRTA1_txtDocTitle"', t)
        self.assertIn("primitive: date_tab_commit", t)
        self.assertIn('selector: "{prefix}dtpEDate_dateInput"', t)
        self.assertIn("primitive: checkbox_enum", t)
        self.assertIn('enum: {"PC류": 0, "자산": 1, "용역": 2}', t)
        self.assertIn("primitive: radio_enum", t)
        self.assertIn("primitive: select", t)
        self.assertIn('"일반사업"', t)
        self.assertIn("primitive: repeat_row", t)
        self.assertIn('add_anchor: "{prefix}LinkButton1"', t)
        self.assertIn("row_probe: \"input[id*='rptRequet_ctl'][id$='txtItemName']\"", t)
        self.assertIn("item_name: txtItemName", t)
        self.assertIn("maxlength: 100", t)
        self.assertIn("fuAttach", t)
        self.assertIn("FORMID=KR_Fixture", t)
        self.assertIn("draft: true", t)
        self.assertIn("dext_body_frames: [2]", t)
        self.assertIn('frame: "toolbar | about:srcdoc"', t)
        self.assertIn('{id: "btnSave", text: "저장", title: "입력한 내용을 저장합니다."', t)

    def test_keys_unique_and_snake(self):
        self.assertIn("  sa_up_ne_yong:", self.text)
        self.assertIn("  napum_place:", self.text)
        used: set[str] = set()
        self.assertEqual(inv.field_key("txtItemName", used), "item_name")
        self.assertEqual(inv.field_key("txtItemName", used), "item_name_2")

    def test_empty_inventory(self):
        t = inv.fieldmap_draft({"frames": []}, None, "")
        self.assertIn("편집 가능 컨트롤을 찾지 못함", t)
        self.assertIn("앵커 미발견", t)


if __name__ == "__main__":
    unittest.main(verbosity=1)

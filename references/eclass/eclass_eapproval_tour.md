# eclass 전자결재(e-Approval) 화면 투어 — CDP 실측 (2026-09-30)

외부 시스템 지식(코드가 아니라 eclass 서버·화면의 동작). 실측 도구 = `probes/ea_eclass_probe.py`
(읽기 전용, 채널 9333). 원형 프로젝트의 선행 실측(로그인 2층·진입 정책)은
`E:\dev\krs-web-agents\references\eclass_전자결재_세션_진입.md` 가 원본이며 여기서는 요지만 옮겼다.

## 1. 진입 URL 과 프레임 구조

사용자가 e-Approval 메뉴를 열면 다음 URL 이다(포털 셸이 전자결재를 iframe 으로 품는다):

```
https://eclass.krs.co.kr/eClassVer4/Common/Default?title=e-Approval&menu=%2FRealEANet%2FMain%2FMainFrameTA.aspx&menuID=MED00002&newWindow=False&PmenuID=MED00001
```

| 깊이 | 프레임 | URL | 내용 |
|---|---|---|---|
| 0 | (top) | `/eClassVer4/Common/Default?title=e-Approval…` | 포털 셸(상단 메뉴 My Dept·e-DOC·e-Approval…) |
| 1 | `iframe#content-iframe` | `/RealEANet/Main/MainFrameTA.aspx` | 전자결재 셸(제목 "전자 결재") |
| 2 | `REA_contents` | `/RealEANet/Main/MainLeft.aspx?` | 좌측 메뉴: 결재양식함 · 기안함(임시보관함·상신함·완료함·반려함) · 결재함(미결함·진행중·완료함·참조함·반려함) · 전체검색 · 환경설정 · 대리결재지정 · 외부발송목록 |
| 2 | `REA_main` | 기본 `/RealEANet/Dialogs/SelectBaseFormTypeB.aspx?&MID=M00000001&MNAME=결재양식함&MPATH=결재양식함&TMID=M0000002` | 양식선택(결재양식함). 좌측 메뉴 클릭에 따라 바뀐다 |

## 2. 결재양식함(양식선택) — FORMID 카탈로그 추출 방법

- 카테고리 탭: `a[id*="rtsCategorys_ctl"]` — `기안문`(ctl00) · `양식결재`(ctl01). 탭을 바꾸지 않아도 두
  카테고리의 링크가 모두 DOM 에 있다(비활성 탭은 `visible=false`).
- 양식 링크: `a[onclick*="OpenAppDocWin"]` — `onclick="javascript:return OpenAppDocWin('/RealEANET/Main/DocumentView.aspx?FORMID=<FORMID>&DOCID=&GROUPID=0&MDTID=0&DID=0&ISMODIFY=0&OLDDOC=&ATTYN=0&ALERTMAIL=0&DOCCNT=0&EXEMTD=RETMTD&ACTYPE=0', …)"`.
  아이콘 앵커와 텍스트 앵커가 한 쌍이므로 FORMID 로 유일화한다.
- 2026-09-30 실측 43건(`probes/ea_eclass_probe.py forms`):

| 카테고리 | FORMID | 양식명 |
|---|---|---|
| 기안문 | KR_EA_Form_Eng2 | 기안문(E) |
| 기안문 | KR_EA_Form2 | 기안문 |
| 기안문 | KR_EA_Form2_Test | 기안문_테스트 (정탐·canary 용으로 적합) |
| 기안문 | KR_EA_Form_Out4 | 기안문(외부공문-회장) |
| 기안문 | KR_EA_Form_Out3 | 기안문(외부공문-본부장,원장,팀장) |
| 양식결재 | KR_EA_Form_Account_2 | 일일회계보고서 |
| 양식결재 | KR_BusinessTrip_Report | 출장복명서 |
| 양식결재 | KR_Contribution_Regulation | 강선규칙외부기증 |
| 양식결재 | KR_Maternity_Leave | 산전산후휴가신청서 |
| 양식결재 | KR_Rent_Vehicle | 회사차량이용신청서 |
| 양식결재 | KR_Sick_Leave | 병가신청서 |
| 양식결재 | KR_SW_Request | 소프트웨어개발/개정요청서 |
| 양식결재 | KR_Technical_Report | 선급기술규칙 제/개정 요청서 |
| 양식결재 | KR_BusinessTripOver_Concerting | 국외출장품의서 |
| 양식결재 | KR_BusinessTrip_Concerting | 출장품의서 |
| 양식결재 | KR_DataPrint_Request | 전산자료출력요청서 |
| 양식결재 | KR_Request_Recruit | 인력충원요청서 |
| 양식결재 | KR_ITInfo_Request | 인트라넷 계정 신청서 |
| 양식결재 | KR_Form_Request | 서식요청서 |
| 양식결재 | KR_EA_Welfare_2 | 사내근로복지기금 |
| 양식결재 | KR_Mutual_Aid | 상조회 |
| 양식결재 | KR_Meeting_Minutes | 회의록 |
| 양식결재 | KR_Internet_Phone_Application | 인터넷전화기 사용 신청서 |
| 양식결재 | KR_Proof_Seal | 인감증명,법인등기부등본 |
| 양식결재 | KR_Educational_Change | 교육변경사유서 |
| 양식결재 | KR_Purchase_Order | 구매요청서 |
| 양식결재 | KR_Purchase_Promotion | 구매추진품의서 |
| 양식결재 | KR_PcManageTrans_Req | PC관리전환 신청서 |
| 양식결재 | KR_AssetTake_Confirm | 자산인계인수 확인서 |
| 양식결재 | KR_Training_Record | 자체교육기록 |
| 양식결재 | KR_Outside_Lecture_Report | 외부강의등 신고서 |
| 양식결재 | KR_Near_Miss_Report | Near Miss Report |
| 양식결재 | KR_Accident_Report | Accident Report |
| 양식결재 | KR_Accident_Investigation | Accident Investigation Report |
| 양식결재 | KR_EA_Research_Approval | 연구 과제 승인요청서 |
| 양식결재 | KR_EA_Research_Evaluation | 연구 과제 자체 평가서 |
| 양식결재 | KR_EA_Research_Task | 연구업무품의서 |
| 양식결재 | KR_Service_Execution | 함정분야 용역수행계획 보고서(Plan Report) |
| 양식결재 | KR_WorkingOvertime_Report | 시간외 근무 사후 승인 요청서 |
| 양식결재 | KR_Service_Performance | 함정분야 용역수행결과 보고서(Result Report) |
| 양식결재 | KR_Outside_ActivityPermit | 외부활동 허가 신청서 |
| 양식결재 | KR_Concept_Approval_Request | 개념승인 심의 및 승인 요청서 |
| 양식결재 | KR_Outside_Permission_Notice | 외부활동 허가 통보서 |

## 3. 로그인 2층과 폼 진입 정책 (원형 실측 요지 + 2026-09-30 재확인)

| 층 | 주소 | 셀렉터 | 자동화 |
|---|---|---|---|
| gate SSO / eclass 포털 | `/eClassVer4/Account/Login` | `#tbUserId` · `#tbPassword` · `#loginButton` | 정탐은 하지 않는다(`needs_login` 으로 보고, 사용자 로그인) |
| RealEANet(전자결재) | `/RealEANET/loginbyname.aspx` | `#txtUserName` · `#imgbtnLogin` | 성명 핸드셰이크 1회(`--ea-name`/`KRS_EA_NAME`), 세션 유효 시 화면 없이 통과 |

- **DocumentView 는 `loginbyname.aspx?ReturnUrl=<경로+쿼리>` 로 연다.** 2026-09-30 실측: 유효 세션에서
  `GET loginbyname…` → `302` → `DocumentView.aspx?FORMID=…` 로 성명 입력 없이 통과. 로그인된 세션에서
  DocumentView 직접 진입은 MsgBox("상신하실 수 없습니다…")로 거부된다는 것이 원형 실측(위 원본 문서).
- OTP·기기(PC)인증 화면은 자동 통과하지 않는다 — `needs_otp`/`needs_device_auth` 로 보고하고 사용자 처리.

## 4. DocumentView(폼) 프레임 구조 — KR_EA_Form2_Test 실측

| 프레임 name | URL | 내용 |
|---|---|---|
| (top) | `/RealEANet/Main/DocumentView.aspx?FORMID=…&DOCID=&…` | 컨트롤 없음(프레임 컨테이너) |
| `frameToolBar` | `/RealEANET/Main/Toolbar_Test2.aspx?FORMID=…&DOCID=HER-…` | 툴바 버튼(아래 표). URL 에 `toolbar` 포함 → 툴바 판별 앵커 |
| `frameDocument` | `/RealEANET/Forms/Drafts/<FORMID>.aspx?FORMID=…&DOCID=HER-…` | **폼 본체.** 제목 `#ctl00_ApplineInfoInReportKRTA1_txtDocTitle`(폼 공통 앵커), 본체 컨트롤 접두 `ctl00_ContentPlaceHolder_Content_`(기안문: `txtRecieve`(수신, textarea)·`txtReference`(참조)·`txtJobId`(Job Id)) |
| `frameDocOther` | `/RealEANET/Main/CommentAttachmentInfo.aspx?…` | 의견·첨부 정보 |
| `ifmEdmsDown` | about:blank | EDMS 다운로드용 |
| `dext_frame_ctl00_ContentPlaceHolder_Content_EditorControl1/2` | `/RealEANET/Components/dext5editor/pages/editor_release.html?ver=3.5.…` | DEXT5 본문 편집기(툴바 버튼 프레임) — 편집 영역 `#dext_body`(contenteditable)는 그 **하위 프레임** |

툴바 버튼(`frameToolBar`, `input[type=image]` — 정탐은 절대 클릭하지 않는다):

| id | alt(text) | title |
|---|---|---|
| `btnAISummarize` | AI 검토 | 작성 중인 본문을 AI로 검토합니다 (저장 불필요) |
| `lbtnGianAppLine` | 결재선 지정 | 결재선을 지정합니다 |
| `lbtnGianAttachFile` | 파일첨부 | 파일을 첨부합니다 |
| `lbtnGianAttachDoc` | 기결재 문서첨부 | 결재완료된 문서를 첨부합니다 |
| `lbtnSetup` | 문서설정 | 결재문서 설정을 변경합니다 |
| `lbtnGianSave` | 임시저장 | 입력한 내용을 저장합니다 |
| `lbtnDraftOpinion` | 의견 | 의견을 입력합니다 |
| `lbtnGianReport` | 상신 | 결재문서를 상신합니다 |
| `lbtnGianPreview` | 미리보기 | 저장하셔야 최신 내용을 확인 |
| `lbtnGianClose` | 닫기 | 현재창을 닫습니다 |

## 5. 관찰·제약

- **문서번호 선채번**: DocumentView URL 의 `DOCID=` 가 빈값이어도 툴바·본체 프레임 URL 에는
  `DOCID=HER-2026-000573` 처럼 번호가 이미 붙어 있었다(2026-09-30). 저장 없이 닫았을 때 임시보관함에 남는지는
  미확인 — 정탐을 반복하면 번호가 소비될 수 있으므로 필요 이상 열지 않는다.
- 폼 열기의 네트워크는 document GET 5건(loginbyname 302 → DocumentView → Toolbar → Forms/Drafts → CommentAttachmentInfo)
  + DEXT5 설정 XHR(`dext_editor.xml`, `upload_handler.ashx?dext=test`)뿐 — 폼 데이터 조회용 REST 는 없고 ASP.NET WebForms
  postback(`__doPostBack`) 구조다. 조회 자동화는 UI 조작 또는 postback 재현이어야 한다.
- 폼 본체 라벨은 `<label for>` 가 아니라 표 셀 텍스트라 인벤토리의 `label` 은 휴리스틱(이전 셀·첫 셀·헤더 셀)이며
  비어 있을 수 있다(기안문의 수신·참조가 그 예).
- Chrome 153 / Playwright 1.55 / CDP 채널 9333(원형 프로젝트 KRS 채널과 공유 — spec ② 채널 표).

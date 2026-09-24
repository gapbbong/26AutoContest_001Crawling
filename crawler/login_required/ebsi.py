# -*- coding: utf-8 -*-
"""
EBSi(ebsi.co.kr) 해설 PDF 자동 수집 어댑터
- EBSi 기출문제 "해설" PDF는 로그인 회원만 다운로드할 수 있다. 아이디/비밀번호는 프로그램에
  절대 입력받지 않고, login_interactively()로 뜨는 브라우저 창에서 사용자가 직접 로그인한다
  (base.LoginRequiredCrawler / browser_login.py).
- 로그인된 세션(self._session)으로 EBSi 기출문제 목록 AJAX를 그대로 재현해 과목별 "해설" PDF
  다운로드 경로를 얻고, PyMuPDF(fitz)로 PDF 텍스트를 추출한 뒤 "N. 문항유형" 패턴으로 문항 단위
  블록을 분리해 {문항번호: 해설텍스트} 형태로 돌려준다.
- 채점표(01. ④, 02. ① ...)처럼 문항번호와 모양이 비슷한 줄을 오인하지 않도록, 헤더 줄은
  "숫자. " 뒤에 한글/영문으로 시작하는 설명이 와야만 문항 시작으로 인정한다(채점표는 원문자
  하나만 오므로 걸러진다).
"""
import re
from typing import Any, Dict, List, Optional

from .base import LoginRequiredCrawler

EBSI_LIST_AJAX_URL = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax"
EBSI_DOWNLOAD_PREFIX = "https://wdown.ebsi.co.kr/W61001/01exam"

# 문항 헤더 판정: "12. 세부 내용 추론"처럼 번호 뒤에 한글/영문 설명이 있어야 진짜 헤더로 본다.
# 채점표의 "01. ④" 같은 줄은 원문자 하나뿐이라 이 패턴에 걸리지 않는다.
_QUESTION_HEADER_RE = re.compile(r'(?:^|\n)(\d{1,2})\.\s+([가-힣A-Za-z][^\n]{0,40})\n')
# 다음 지문 그룹 헤더([4~9] 처럼)나 "■ [공통: 독서·문학] 01.③ 02.⑤ ..." 채점표 박스가
# 해설 블록 뒤에 이어 붙어 들어오는 경우, 그 시작 지점에서 블록을 잘라낸다.
_BLOCK_END_RE = re.compile(r'\n(?:\[\d{1,2}\s*[~\-]\s*\d{1,2}\]|■)')
# 해설 블록 안에서 새 줄로 유지해야 하는(=PDF의 단순 줄바꿈이 아니라 진짜 문단 구분인) 시작 표지.
# 이 표지로 시작하지 않는 줄은 PDF가 폭에 맞춰 끊은 것뿐이므로 앞 줄에 공백으로 이어붙인다.
_KEEP_LINE_BREAK_PREFIXES = ('정답해설', '정답 ', '정답:', '[오답피하기]', '지문해설', '[주제]')


class EBSiSolutionCrawler(LoginRequiredCrawler):
    source_name = "EBSi"
    login_url = "https://www.ebsi.co.kr/ebs/pot/potl/login.ebs"
    login_notice = "EBSi 해설 PDF는 로그인 회원만 다운로드할 수 있습니다 — 실행 시 뜨는 브라우저 창에서 직접 로그인하세요."

    def _fetch_exam_list_authenticated(self, year: int, grade: int) -> List[Dict[str, Any]]:
        raise NotImplementedError("EBSiSolutionCrawler는 해설 수집 전용입니다 — fetch_solution_links()를 사용하세요.")

    def _fetch_questions_authenticated(self, exam_id: str, subject_code: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("EBSiSolutionCrawler는 해설 수집 전용입니다 — fetch_solution_links()를 사용하세요.")

    def fetch_solution_links(self, year: int, month: Optional[int] = None, target_cd: str = "D300") -> List[Dict[str, str]]:
        """
        로그인된 세션으로 EBSi 기출문제 목록을 조회해 과목별 "해설" PDF 다운로드 경로를 추출한다.
        month를 생략하면(수능처럼 월이 없는 경우) 3~12월 전체를 조회 범위로 둔다(EBSi 목록 화면의
        기본 동작과 동일).
        """
        if not self.is_logged_in():
            return []

        month_list = f"{month:02d}" if month else "03,04,05,06,07,08,09,10,11,12"
        resp = self._session.post(
            EBSI_LIST_AJAX_URL,
            data={
                "targetCd": target_cd,
                "yearList": str(year),
                "monthList": month_list,
                "arOrd": "1,2,3,4,5,,6,7,8",
                "subjIdList": "firstEnter",
                "currentPage": "1",
            },
        )
        resp.encoding = "utf-8"
        html = resp.text

        results = []
        for block in re.split(r'(?=<div class="qus_tit">)', html):
            title_m = re.search(r'<div class="qus_tit">([^<]+)</div>', block)
            solution_m = re.search(r"goDownLoadH\('([^']+\.pdf)'", block)
            subject_m = re.search(r'<span class="t_col_\w+">([^<]+)</span>', block)
            if title_m and solution_m:
                results.append({
                    "subject_label": subject_m.group(1).strip() if subject_m else "",
                    "exam_title": title_m.group(1).replace("&nbsp;", " ").strip(),
                    "solution_pdf_url": EBSI_DOWNLOAD_PREFIX + solution_m.group(1),
                })
        return results

    def download_solution_pdf(self, pdf_url: str) -> bytes:
        if not self.is_logged_in():
            raise RuntimeError("로그인이 필요합니다.")
        resp = self._session.get(pdf_url)
        resp.raise_for_status()
        return resp.content

    def parse_solution_pdf(self, pdf_bytes: bytes) -> Dict[int, str]:
        """해설 PDF 텍스트를 문항번호 단위로 분리해 {문항번호: 해설텍스트} 로 반환"""
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            full_text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()

        matches = list(_QUESTION_HEADER_RE.finditer(full_text))
        results: Dict[int, str] = {}
        for i, m in enumerate(matches):
            q_num = int(m.group(1))
            if not (1 <= q_num <= 45):
                continue
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            block = full_text[start:end].strip()
            block_end = _BLOCK_END_RE.search(block)
            if block_end:
                block = block[:block_end.start()].strip()
            block = self._clean_solution_block(block)
            if block:
                results[q_num] = block
        return results

    @staticmethod
    def _clean_solution_block(text: str) -> str:
        """PDF가 폭에 맞춰 끊어놓은 줄바꿈을 문장으로 다시 이어붙인다. "정답해설/정답/
        [오답피하기]/지문해설/[주제]"로 시작하는 줄만 진짜 문단 구분으로 보고 새 줄로 유지한다."""
        out: List[str] = []
        for raw_line in text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            if out and not line.startswith(_KEEP_LINE_BREAK_PREFIXES):
                out[-1] = f"{out[-1]} {line}"
            else:
                out.append(line)
        out = [
            EBSiSolutionCrawler._split_odappihagi_line(line) if line.startswith('[오답피하기]') else line
            for line in out
        ]
        return '\n'.join(out)

    @staticmethod
    def _split_odappihagi_line(line: str) -> str:
        """"[오답피하기] ①, ② ~. ③ ~. ⑤ ~." 한 줄을 선택지 단위로 줄바꿈한다.
        "①, ②"처럼 콤마로 묶여 같은 설명을 공유하는 선택지들은 한 줄에 같이 둔다."""
        body = line[len('[오답피하기]'):].strip()
        if not body:
            return line
        tokens = re.split(r'([①②③④⑤])', body)
        choices: List[str] = []
        buf = ""
        for tok in tokens:
            if tok in ('①', '②', '③', '④', '⑤'):
                if buf.rstrip().endswith((',', '、')):
                    buf += tok
                else:
                    if buf.strip():
                        choices.append(buf.strip())
                    buf = tok
            else:
                buf += tok
        if buf.strip():
            choices.append(buf.strip())
        if not choices:
            return line
        return '[오답피하기]\n' + '\n'.join(choices)

    def collect_solutions_for_subject(self, year: int, grade: int, subject_keyword: str,
                                       month: Optional[int] = None) -> Dict[int, str]:
        """subject_keyword(예: '화법과 작문', '언어와 매체', '미적분')가 exam_title에 포함된
        첫 번째 해설 PDF를 받아 파싱까지 마친 {문항번호: 해설텍스트}를 반환한다. 매칭 실패 시 빈 dict.
        EBSi 쪽 제목은 띄어쓰기가 다를 수 있어(예: '생활과 윤리' vs '생활과윤리') 공백을 제거하고 비교한다."""
        links = self.fetch_solution_links(year=year, month=month)
        keyword_norm = re.sub(r'\s+', '', subject_keyword)
        target = next((l for l in links if keyword_norm in re.sub(r'\s+', '', l["exam_title"])), None)
        if not target:
            return {}
        pdf_bytes = self.download_solution_pdf(target["solution_pdf_url"])
        return self.parse_solution_pdf(pdf_bytes)

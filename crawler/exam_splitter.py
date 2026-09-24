# -*- coding: utf-8 -*-
"""
기출 시험지 문서 자동 분할 및 문항 구조화 파서
- PyMuPDF(fitz) 및 정규식을 활용하여 통파일 시험지에서 1~30/45번 문항, 지문, 보기 ①~⑤, 정답, 해설을 고속으로 분할 추출
"""
import os
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

class ExamSplitter:
    """통파일 기출 시험지 자동 분할 및 구조화 파서"""
    def __init__(self):
        self.fitz_available = FITZ_AVAILABLE

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF 파일에서 전체 텍스트 추출"""
        if not os.path.exists(pdf_path) or not self.fitz_available:
            return ""
        try:
            doc = fitz.open(pdf_path)
            full_text = []
            for page in doc:
                full_text.append(page.get_text())
            doc.close()
            return "\n".join(full_text)
        except Exception as e:
            logger.error(f"PDF 텍스트 추출 오류: {e}")
            return ""

    def split_raw_exam_text(self, raw_text: str, default_subject: str = "수학", year: int = 2026) -> List[Dict[str, Any]]:
        """
        시험지 원본 텍스트를 문항 번호(1. ~ 45.) 및 보기(①~⑤)를 기준으로 개별 문항 딕셔너리 리스트로 분할

        ※ 이 함수는 "지문 분할"만 담당한다. 정답/정답률/단원 분류는 지어내지 않는다 —
        EBSi가 실제로 공개하는 출처가 없으면 None/미분류로 남겨두고, 호출자(ebsi_crawler.py)가
        오답률 API 등 실제 데이터로 채워 넣을 수 있으면 그때 채운다.
        """
        questions = []
        # 문항 번호 분할 정규식 (예: "1.", "2.", "30.")
        q_blocks = re.split(r'\n\s*([0-9]{1,2})\.\s+', "\n" + raw_text)

        if len(q_blocks) <= 1:
            return questions

        for i in range(1, len(q_blocks), 2):
            q_num = int(q_blocks[i])
            q_content = q_blocks[i+1].strip()

            # 다음 지문 또는 페이지 헤더(홀수형/짝수형 등) 누출 방지
            leak_match = re.search(r'\n(?:\s*\d+\s*\n)?\s*(?:\d{4}학년도\s+대학수학능력시험|\d{4}학년도\s+.*시험 문제지|\[\s*\d+\s*[～~-]\s*\d+\s*\]\s*다음\s*글을|홀수형|짝수형)', q_content)
            if leak_match:
                q_content = q_content[:leak_match.start()].strip()

            # 배점 추출 (예: [2점], [3점], [4점]) - 실제 지문에 인쇄된 값. 없으면 2점으로 기본 처리.
            score_match = re.search(r'\[([2-4])점\]', q_content)
            score = int(score_match.group(1)) if score_match else 2

            questions.append({
                "question_number": q_num,
                "subject_name": default_subject,
                "major_chapter": "단원 미분류",  # EBSi가 단원(교육과정) 정보를 제공하지 않음 - 수동 분류 필요
                "middle_chapter": "단원 미분류",
                "minor_chapter": "",
                "score": score,
                "answer": None,       # 실제 정답 데이터가 있으면 호출자가 채움 (없으면 None 유지, 지어내지 않음)
                "correct_rate": None, # 실제 오답률 데이터가 있으면 호출자가 채움
                "question_text": f"[{year}학년도 {default_subject} {q_num}번]\n\n" + q_content,
                "solution_text": ""   # 실제 해설 PDF에서 채우기 전까지는 비워둠 (지어낸 문장 삽입 금지)
            })

        return questions

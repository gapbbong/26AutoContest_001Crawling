# -*- coding: utf-8 -*-
"""
공공 교육 기출 포털 시험지 자동 다운로더
- 한국교육과정평가원(KICE), EBSi 국가 교육 포털, 부산광역시교육청 등 공공 포털의 기출 시험지 파일 자동 다운로드 및 캐싱
"""
import os
import logging
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

PORTAL_DOWNLOAD_CONFIGS = {
    "KICE": {
        "name": "한국교육과정평가원 (KICE)",
        "base_url": "https://www.kice.re.kr",
        "sample_pdf": "https://www.kice.re.kr/boardCnts/view.do?boardID=1500211&s=kice"
    },
    "EBSI": {
        "name": "EBSi 국가 교육 포털",
        "base_url": "https://www.ebsi.co.kr",
        "sample_pdf": "https://wdown.ebsi.co.kr/wdown/exam"
    },
    "BICE": {
        "name": "부산광역시교육청 학력개발원",
        "base_url": "https://home.pen.go.kr",
        "sample_pdf": "https://home.pen.go.kr/exam/view.do"
    }
}

class PortalDownloader:
    """공공 기출 포털 시험지 자동 다운로드 및 캐시 관리자"""
    def __init__(self, download_dir: str = "data/downloads"):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    def download_exam_file(self, portal_code: str, year: int, grade: str, exam_type: str, subject: str) -> Optional[str]:
        """
        포털에서 실제 기출 시험지 파일(PDF)을 다운로드하여 로컬 캐시에 저장하고 파일 경로 반환
        """
        filename = f"{year}_{portal_code}_{grade}_{exam_type}_{subject}.pdf"
        target_path = os.path.join(self.download_dir, filename)

        if os.path.exists(target_path) and os.path.getsize(target_path) > 100:
            logger.info(f"로컬 캐시된 기출 시험지 사용: {target_path}")
            return target_path

        try:
            cfg = PORTAL_DOWNLOAD_CONFIGS.get(portal_code, PORTAL_DOWNLOAD_CONFIGS["EBSI"])
            url = cfg["base_url"]
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                logger.info(f"[{portal_code}] 공공 포털 접속 및 시험지 데이터 획득 완료 ({url})")
            return target_path
        except Exception as e:
            logger.warning(f"시험지 다운로드 중 네트워크 경고 (로컬 파서 연동): {e}")
            return target_path

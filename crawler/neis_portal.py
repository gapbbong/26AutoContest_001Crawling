# -*- coding: utf-8 -*-
"""
나이스(NEIS) 교육정보 개방 포털 연동 (open.neis.go.kr)
- 개인 로그인이 아닌 발급형 API 인증키(NEIS_API_KEY 환경변수) 기반 오픈API. 로그인 불필요.
- 주의: NEIS 오픈API는 학교기본정보/학사일정/시간표/학교급식 등 행정 메타데이터만 제공하며
  기출문제 문항 콘텐츠는 제공하지 않는다. 따라서 "기출문제 수집" 파이프라인이 아닌
  보조 참고자료(학교 정보 조회) 용도로만 사용한다.
"""
import os
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

NEIS_BASE_URL = "https://open.neis.go.kr/hub"


class NeisPortalClient:
    """NEIS 오픈API 학교 메타데이터 조회 클라이언트 (기출문제 콘텐츠 없음, 보조 정보용)"""

    def __init__(self):
        self.api_key = os.environ.get("NEIS_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_school_info(self, school_name: str, edu_office_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """학교기본정보 조회 (schoolInfo). 문항 콘텐츠가 아닌 학교 메타데이터만 반환."""
        if not self.is_configured():
            logger.info("NEIS_API_KEY 미설정 - 학교 정보 조회 건너뜀")
            return []

        params = {
            "KEY": self.api_key,
            "Type": "json",
            "pIndex": 1,
            "pSize": 20,
            "SCHUL_NM": school_name,
        }
        if edu_office_code:
            params["ATPT_OFCDC_SC_CODE"] = edu_office_code

        try:
            resp = requests.get(f"{NEIS_BASE_URL}/schoolInfo", params=params, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("schoolInfo", [{}, {}])[1].get("row", [])
            return rows
        except Exception as e:
            logger.warning(f"NEIS 학교 정보 조회 실패: {e}")
            return []

    def fetch_academic_calendar(self, school_code: str, edu_office_code: str, year: int) -> List[Dict[str, Any]]:
        """학사일정 조회 (SchoolSchedule). 문항 콘텐츠가 아닌 일정 메타데이터만 반환."""
        if not self.is_configured():
            logger.info("NEIS_API_KEY 미설정 - 학사일정 조회 건너뜀")
            return []

        params = {
            "KEY": self.api_key,
            "Type": "json",
            "pIndex": 1,
            "pSize": 100,
            "ATPT_OFCDC_SC_CODE": edu_office_code,
            "SD_SCHUL_CODE": school_code,
            "AA_YMD": f"{year}0101-{year}1231",
        }
        try:
            resp = requests.get(f"{NEIS_BASE_URL}/SchoolSchedule", params=params, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("SchoolSchedule", [{}, {}])[1].get("row", [])
            return rows
        except Exception as e:
            logger.warning(f"NEIS 학사일정 조회 실패: {e}")
            return []

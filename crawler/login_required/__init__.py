# -*- coding: utf-8 -*-
"""
로그인 필요 출처 어댑터 레지스트리
- 인디스쿨, 아이스크림, e학습터/위두랑 등 개인 계정 로그인이 있어야 자료 다운로드가 가능한 출처를 위한 확장 슬롯.
- 기본 공공 출처(EBSi/KICE/부산교육청/에듀넷/기초학력센터)와 달리 계정 정보가 있어야만 동작하므로
  UI에서는 기본 비활성(미체크) 상태로 노출하고, 자격증명이 없으면 항상 안전하게 건너뛴다.
"""
from typing import Dict
from .base import LoginRequiredCrawler
from .ebsi import EBSiSolutionCrawler

# 새 로그인 출처를 추가할 때는 여기에 한 줄만 등록하면 UI/실행 파이프라인에 자동 노출된다.
# 인디스쿨: 초등교사 대상 커뮤니티(자체제작 학습자료 중심)로 이 프로그램의 중·고등 기출문제
# 수집 목적과 맞지 않아 제외함.
LOGIN_REQUIRED_SOURCES: Dict[str, Dict] = {
    "ebsi_solution": {
        "class": EBSiSolutionCrawler,
        "name": "EBSi 해설(정답 및 해설 PDF)",
        "notice": EBSiSolutionCrawler.login_notice,
    },
}


def get_source(key: str) -> LoginRequiredCrawler:
    cfg = LOGIN_REQUIRED_SOURCES[key]
    return cfg["class"]()


def list_sources() -> Dict[str, Dict]:
    return LOGIN_REQUIRED_SOURCES

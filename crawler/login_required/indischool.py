# -*- coding: utf-8 -*-
"""
인디스쿨(indischool.com) 어댑터 — 구조만 준비된 비활성 스텁
- 초등교사 인증회원제 커뮤니티라 정회원 가입 및 개인 계정 로그인이 있어야 자료실 접근이 가능하다.
- 로그인은 아이디/비번을 프로그램에 입력받지 않고, 브라우저 창을 띄워 사용자가 직접 로그인한다
  (login_interactively() → base.LoginRequiredCrawler / browser_login.py).
- 로그인 이후 실제 자료 목록/문항 파싱 로직은 계정 확보 및 이용약관 검토 후 구현 예정.
"""
from typing import List, Dict, Any

from .base import LoginRequiredCrawler


class IndischoolCrawler(LoginRequiredCrawler):
    source_name = "인디스쿨"
    login_url = "https://indischool.com/login"
    login_notice = "정회원 가입 및 로그인 후 자료실 접근 가능 — 실행 시 뜨는 브라우저 창에서 직접 로그인하세요."

    def _fetch_exam_list_authenticated(self, year: int, grade: int) -> List[Dict[str, Any]]:
        # TODO: self._session으로 로그인된 요청을 보내 자료실 목록 조회 구현
        raise NotImplementedError("인디스쿨 자료 조회 로직 미구현 (스텁)")

    def _fetch_questions_authenticated(self, exam_id: str, subject_code: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("인디스쿨 문항 파싱 로직 미구현 (스텁)")

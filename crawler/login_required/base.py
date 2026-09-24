# -*- coding: utf-8 -*-
"""
로그인 필요 출처 공통 베이스 클래스
- crawler/base.py의 BaseCrawler와 동일한 인터페이스(fetch_exam_list/fetch_questions)를 따르되,
  아이디/비밀번호를 프로그램에 입력받지 않는다. 대신 브라우저 창을 띄워 사용자가 직접 로그인하고,
  로그인 완료된 세션 쿠키만 넘겨받아 이후 요청에 재사용한다 (login_required/browser_login.py).
- 로그인 전에는 절대 실제 요청을 보내지 않고 안전하게 빈 결과만 반환한다.
"""
from typing import List, Dict, Any, Optional

import requests

from ..base import BaseCrawler
from .browser_login import interactive_browser_login


class LoginRequiredCrawler(BaseCrawler):
    #: 하위 클래스에서 지정: 출처 표시명
    source_name: str = "로그인 필요 출처"
    #: 하위 클래스에서 지정: 로그인 페이지 URL
    login_url: str = ""
    #: 하위 클래스에서 지정: UI에 보여줄 안내 문구
    login_notice: str = "브라우저 창에서 사용자가 직접 로그인해야 합니다."

    def __init__(self):
        self._session: Optional[requests.Session] = None

    def is_logged_in(self) -> bool:
        return self._session is not None

    def login_interactively(self, timeout_sec: int = 300, browser: str = "edge") -> None:
        """브라우저 창을 열어 사용자가 직접 로그인. 완료되면 세션 쿠키를 내부에 보관한다."""
        if not self.login_url:
            raise NotImplementedError(f"{self.source_name}: login_url이 설정되지 않았습니다.")
        self._session = interactive_browser_login(self.login_url, timeout_sec=timeout_sec, browser=browser)

    def fetch_exam_list(self, year: int, grade: int) -> List[Dict[str, Any]]:
        if not self.is_logged_in():
            return []
        return self._fetch_exam_list_authenticated(year, grade)

    def fetch_questions(self, exam_id: str, subject_code: str) -> List[Dict[str, Any]]:
        if not self.is_logged_in():
            return []
        return self._fetch_questions_authenticated(exam_id, subject_code)

    # 하위 클래스가 실제 구현을 채워 넣는 지점 (self._session으로 로그인된 요청을 보낸다)
    def _fetch_exam_list_authenticated(self, year: int, grade: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def _fetch_questions_authenticated(self, exam_id: str, subject_code: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

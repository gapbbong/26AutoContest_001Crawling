# -*- coding: utf-8 -*-
"""
사용자 수동 브라우저 로그인 → 세션 쿠키 이전 헬퍼
- 아이디/비밀번호는 프로그램에 절대 입력받거나 저장하지 않는다. Edge 브라우저 창을 띄우면
  사용자가 직접 로그인하고, 로그인 완료가 감지되면 그 세션 쿠키만 requests.Session으로 옮겨
  이후의 가벼운 HTTP 요청(자료 목록/다운로드)에 재사용한다.
- Edge를 기본으로 쓰는 이유: Windows 11에 기본 설치되어 있어 학교 업무망 PC에서도
  별도 설치 없이 바로 동작한다 (Chromium 기반이라 Selenium 호환성은 Chrome과 동일).
"""
import time
import logging

import requests

logger = logging.getLogger(__name__)


class BrowserLoginTimeout(Exception):
    """제한 시간 내에 로그인이 완료되지 않았을 때"""


def interactive_browser_login(login_url: str, timeout_sec: int = 300, browser: str = "edge") -> requests.Session:
    """
    브라우저 창을 열어 사용자가 직접 로그인하게 하고, 로그인 완료 후 세션 쿠키를 requests.Session으로 이전한다.

    Args:
        login_url: 로그인 페이지 URL
        timeout_sec: 사용자가 로그인을 완료할 때까지 최대 대기 시간(초)
        browser: "edge"(기본, Windows 11 내장) 또는 "chrome"

    Returns:
        로그인 세션 쿠키가 담긴 requests.Session
    """
    try:
        from selenium import webdriver
    except ImportError as e:
        raise RuntimeError("selenium이 설치되어 있지 않습니다. `pip install selenium`으로 설치 후 다시 시도하세요.") from e

    if browser == "chrome":
        driver = webdriver.Chrome()
    else:
        driver = webdriver.Edge()

    try:
        driver.get(login_url)
        logger.info(f"브라우저 로그인 창 오픈: {login_url} (사용자 로그인 대기, 최대 {timeout_sec}초)")

        start = time.time()
        logged_in = False
        while time.time() - start < timeout_sec:
            # 로그인 성공 시 대부분의 사이트는 로그인 페이지에서 다른 URL로 리다이렉트된다.
            if driver.current_url.rstrip("/") != login_url.rstrip("/"):
                logged_in = True
                break
            time.sleep(1)

        if not logged_in:
            raise BrowserLoginTimeout(f"{timeout_sec}초 내에 로그인이 완료되지 않았습니다 (로그인 창을 닫았거나 시간 초과).")

        selenium_cookies = driver.get_cookies()
    finally:
        driver.quit()

    session = requests.Session()
    for c in selenium_cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain"))
    return session

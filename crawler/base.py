from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseCrawler(ABC):
    @abstractmethod
    def fetch_exam_list(self, year: int, grade: int) -> List[Dict[str, Any]]:
        """연도 및 학년별 기출 시험 목록 조회"""
        pass

    @abstractmethod
    def fetch_questions(self, exam_id: str, subject_code: str) -> List[Dict[str, Any]]:
        """해당 시험 및 과목의 문항/정답/해설/단원 정보 크롤링"""
        pass

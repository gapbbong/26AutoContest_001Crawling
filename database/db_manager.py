import sqlite3
import os
import json
import re
from typing import List, Dict, Any, Optional, Union

# 평가원/EBS/한컴 전용 비표준 PUA 특수문자를 표준 유니코드로 변환
PUA_SYMBOL_MAP = {
    '\U000f0854': '『',   # 여는 겹낫표
    '\U000f0855': '』',   # 닫는 겹낫표
    '\U000f02b1': '㉠',   # 설문/보기 기호 (1)
    '\U000f02b2': '㉡',   # 설문/보기 기호 (2)
    '\U000f02b3': '㉢',   # 설문/보기 기호 (3)
    '\U000f02b4': '㉣',   # 설문/보기 기호 (4)
    '\U000f0802': '• ',   # 글머리 기호
    '\U000f003b': '▼ ',   # 아래 화살표
}

def normalize_pua_symbols(text: str) -> str:
    """비표준 PUA 특수문자 및 깨진 흐름도/다이어그램을 표준 서식으로 치환"""
    if not text:
        return ""
    for pua_char, std_char in PUA_SYMBOL_MAP.items():
        if pua_char in text:
            text = text.replace(pua_char, std_char)

    # 2단 PDF 추출 시 줄바꿈 왜곡으로 세로로 깨진 가로 흐름도(입력 ⇨ 단계 ⇨ 출력) 구조 자동 복원
    # 패턴: (가) \n ⇨ \n A 단계 \n ⇨ \n (나) \n ㉠ \n ㉡ \n ㉢
    broken_flow_patterns = [
        (
            r'\(가\)\s*\n\s*⇨\s*\n\s*([A-Za-z0-9가-힣\s]+단계)\s*\n\s*⇨\s*\n\s*\(나\)\s*\n\s*([㉠-㉭\s]+)',
            r'<자료>\n[ (가) : ㉠, ㉡, ㉢ ]  ⇨  [ \1 ]  ⇨  [ (나) : ㉠, ㉡, ㉢ ]'
        ),
    ]
    for pattern, repl in broken_flow_patterns:
        text = re.sub(pattern, repl, text)

    return text

class QuestionDB:
    def __init__(self, db_path: str = "data/questions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_code TEXT UNIQUE,
                year INTEGER,
                month INTEGER,
                grade INTEGER,
                exam_type TEXT, -- 수능, 6월 모평, 9월 모평, 3월 학평, 4월 학평, 7월 학평, 10월 학평
                title TEXT,
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER,
                question_num INTEGER,
                subject_code TEXT,
                subject_name TEXT, -- 수학, 국어, 영어, 한국사, 물리학Ⅰ 등
                major_chapter TEXT, -- 대단원
                middle_chapter TEXT, -- 중단원
                minor_chapter TEXT, -- 소단원
                score INTEGER DEFAULT 2, -- 배점 (2, 3, 4 등)
                answer TEXT, -- 정답 (1~5 or 단답형 숫자)
                correct_rate REAL, -- 정답률 (%)
                question_text TEXT,
                question_image_path TEXT,
                solution_text TEXT,
                solution_image_path TEXT,
                extra_data TEXT, -- JSON 포맷 (선택지, 난이도 등)
                FOREIGN KEY (exam_id) REFERENCES exams(id)
            );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subject ON questions(subject_name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_major_chapter ON questions(major_chapter);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_middle_chapter ON questions(middle_chapter);")
            conn.commit()

    def insert_exam(self, exam_data: Dict[str, Any]) -> int:
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO exams (exam_code, year, month, grade, exam_type, title, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exam_data.get('exam_code'),
                exam_data.get('year'),
                exam_data.get('month'),
                exam_data.get('grade'),
                exam_data.get('exam_type'),
                exam_data.get('title'),
                exam_data.get('source_url'),
                exam_data.get('created_at', now_str)
            ))
            conn.commit()
            return cursor.lastrowid

    def update_solution_texts(self, year: int, grade: int, exam_type: str, subject_name: str,
                               solutions: Dict[int, str]) -> int:
        """EBSi 등 외부에서 수집한 {문항번호: 해설텍스트}를 exams(year/grade/exam_type)와
        questions.subject_name이 일치하는 문항들에 채워 넣는다. 갱신된 행 수를 반환한다."""
        if not solutions:
            return 0
        updated = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM exams WHERE year = ? AND grade = ? AND exam_type = ?",
                (year, grade, exam_type)
            )
            exam_ids = [row[0] for row in cursor.fetchall()]
            if not exam_ids:
                return 0
            placeholders = ",".join("?" * len(exam_ids))
            for q_num, sol_text in solutions.items():
                cursor.execute(
                    f"""UPDATE questions SET solution_text = ?
                        WHERE exam_id IN ({placeholders}) AND subject_name = ? AND question_num = ?""",
                    (sol_text, *exam_ids, subject_name, q_num)
                )
                updated += cursor.rowcount
            conn.commit()
        return updated

    def get_latest_generation_time(self) -> str:
        """최근 문제 생성일/최근 크롤링 일시 조회"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(created_at) FROM exams")
                res = cursor.fetchone()
                if res and res[0]:
                    return str(res[0])[:16]
        except Exception:
            pass
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def get_total_question_count(self) -> int:
        """현재 DB에 저장된 유효 총 문항 수 조회 (exams 테이블과 JOIN하여 100% 일치 보장)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM questions q JOIN exams e ON q.exam_id = e.id")
                res = cursor.fetchone()
                if res and res[0] is not None:
                    return int(res[0])
        except Exception:
            pass
        return 0

    def count_questions(self,
                        subject_name: Optional[str] = None,
                        grade: Optional[int] = None,
                        year: Optional[int] = None,
                        exam_type: Optional[str] = None,
                        source_portal: Optional[str] = None,
                        major_chapter: Optional[str] = None) -> int:
        """조건에 부합하는 문항 수 카운트"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT COUNT(*)
            FROM questions q
            JOIN exams e ON q.exam_id = e.id
            WHERE 1=1
            """
            params = []

            if source_portal and source_portal != "전체" and "전체" not in str(source_portal):
                if "EBS" in source_portal:
                    query += " AND (e.source_url LIKE '%ebsi%' OR e.source_url LIKE '%EBS%' OR e.title LIKE '%EBS%')"
                elif "평가원" in source_portal or "KICE" in source_portal:
                    query += " AND (e.source_url LIKE '%kice%' OR e.source_url LIKE '%평가원%' OR e.exam_type LIKE '%수능%' OR e.exam_type LIKE '%모의평가%')"
                elif "부산" in source_portal or "교육청" in source_portal:
                    query += " AND (e.source_url LIKE '%pen.go.kr%' OR e.source_url LIKE '%부산%' OR e.exam_type LIKE '%학력평가%' OR e.exam_type LIKE '%총괄%')"
                elif "에듀넷" in source_portal or "KERIS" in source_portal or "티-클리어" in source_portal:
                    query += " AND (e.source_url LIKE '%edunet%' OR e.source_url LIKE '%KERIS%' OR e.source_url LIKE '%에듀넷%' OR e.title LIKE '%에듀넷%')"
                elif "기초학력" in source_portal or "KEDI" in source_portal:
                    query += " AND (e.source_url LIKE '%kedi%' OR e.source_url LIKE '%기초학력%' OR e.source_url LIKE '%basiclearning%' OR e.title LIKE '%기초학력%')"
                else:
                    query += " AND (e.source_url LIKE ? OR e.title LIKE ?)"
                    params.extend([f"%{source_portal}%", f"%{source_portal}%"])

            if subject_name and subject_name != "전체" and "전체" not in str(subject_name):
                query += " AND q.subject_name = ?"
                params.append(subject_name)
            if grade and grade != 0 and grade != "전체" and "전체" not in str(grade):
                try:
                    query += " AND e.grade = ?"
                    params.append(int(grade))
                except Exception:
                    pass
            if year and year != "전체" and "전체" not in str(year):
                try:
                    query += " AND e.year = ?"
                    params.append(int(year))
                except Exception:
                    pass
            if exam_type and exam_type != "전체" and "전체" not in str(exam_type):
                query += " AND e.exam_type LIKE ?"
                params.append(f"%{exam_type}%")
            if major_chapter and major_chapter != "전체":
                query += " AND q.major_chapter = ?"
                params.append(major_chapter)

            cursor.execute(query, params)
            res = cursor.fetchone()
            return int(res[0]) if res and res[0] is not None else 0

    def clear_database(self):
        """데이터베이스 초기화 (새로 구축 모드용)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM questions;")
            cursor.execute("DELETE FROM exams;")
            conn.commit()

    def insert_questions(self, questions: List[Dict[str, Any]]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for q in questions:
                # 중복 방지: 동일 시험의 동일 문항번호 삭제 후 최신 데이터 삽입 (Smart Upsert)
                cursor.execute("DELETE FROM questions WHERE exam_id = ? AND question_num = ?", (q.get('exam_id'), q.get('question_num')))
                cursor.execute("""
                INSERT INTO questions (
                    exam_id, question_num, subject_code, subject_name,
                    major_chapter, middle_chapter, minor_chapter,
                    score, answer, correct_rate, question_text,
                    question_image_path, solution_text, solution_image_path, extra_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    q.get('exam_id'),
                    q.get('question_num'),
                    q.get('subject_code'),
                    q.get('subject_name'),
                    q.get('major_chapter'),
                    q.get('middle_chapter'),
                    q.get('minor_chapter'),
                    q.get('score', 2),
                    str(q.get('answer', '')),
                    q.get('correct_rate'),
                    normalize_pua_symbols(q.get('question_text', '')),
                    q.get('question_image_path', ''),
                    normalize_pua_symbols(q.get('solution_text', '')),
                    q.get('solution_image_path', ''),
                    json.dumps(q.get('extra_data', {}), ensure_ascii=False)
                ))
            conn.commit()

    def search_questions(self, 
                         subject_name: Optional[Union[str, List[str]]] = None,
                         grade: Optional[Union[int, str, List[Union[int, str]]]] = None,
                         year_from: Optional[int] = None,
                         year_to: Optional[int] = None,
                         exam_type: Optional[Union[str, List[str]]] = None,
                         source_portal: Optional[Union[str, List[str]]] = None,
                         major_chapter: Optional[str] = None,
                         middle_chapter: Optional[str] = None,
                         keyword: Optional[str] = None,
                         years: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
            SELECT q.*, e.year, e.month, e.grade, e.exam_type, e.title as exam_title, e.source_url
            FROM questions q
            JOIN exams e ON q.exam_id = e.id
            WHERE 1=1
            """
            params = []

            # 1. source_portal (단일 또는 리스트)
            if source_portal:
                portals_list = [source_portal] if isinstance(source_portal, str) else list(source_portal)
                portals_list = [p for p in portals_list if p and p != "전체" and "전체" not in str(p)]
                if portals_list:
                    portal_clauses = []
                    for p in portals_list:
                        if "EBS" in p:
                            portal_clauses.append("(e.source_url LIKE '%ebsi%' OR e.source_url LIKE '%EBS%' OR e.title LIKE '%EBS%')")
                        elif "평가원" in p or "KICE" in p:
                            portal_clauses.append("(e.source_url LIKE '%kice%' OR e.source_url LIKE '%평가원%' OR e.exam_type LIKE '%수능%' OR e.exam_type LIKE '%모의평가%')")
                        elif "부산" in p or "교육청" in p:
                            portal_clauses.append("(e.source_url LIKE '%pen.go.kr%' OR e.source_url LIKE '%부산%' OR e.exam_type LIKE '%학력평가%' OR e.exam_type LIKE '%총괄%')")
                        elif "에듀넷" in p or "KERIS" in p or "티-클리어" in p:
                            portal_clauses.append("(e.source_url LIKE '%edunet%' OR e.source_url LIKE '%KERIS%' OR e.source_url LIKE '%에듀넷%' OR e.title LIKE '%에듀넷%')")
                        elif "기초학력" in p or "KEDI" in p:
                            portal_clauses.append("(e.source_url LIKE '%kedi%' OR e.source_url LIKE '%기초학력%' OR e.source_url LIKE '%basiclearning%' OR e.title LIKE '%기초학력%')")
                        else:
                            portal_clauses.append("(e.source_url LIKE ? OR e.title LIKE ?)")
                            params.extend([f"%{p}%", f"%{p}%"])
                    if portal_clauses:
                        query += f" AND ({' OR '.join(portal_clauses)})"

            # 2. subject_name (단일 또는 리스트)
            if subject_name:
                subj_list = [subject_name] if isinstance(subject_name, str) else list(subject_name)
                subj_list = [s for s in subj_list if s and s != "전체" and "전체" not in str(s)]
                if subj_list:
                    placeholders = ", ".join(["?"] * len(subj_list))
                    query += f" AND q.subject_name IN ({placeholders})"
                    params.extend(subj_list)

            # 3. grade (단일 또는 리스트)
            if grade:
                raw_grades = [grade] if isinstance(grade, (int, str)) else list(grade)
                valid_grades = []
                for g in raw_grades:
                    if g and g != 0 and g != "전체" and "전체" not in str(g):
                        try:
                            valid_grades.append(int(g))
                        except Exception:
                            pass
                if valid_grades:
                    placeholders = ", ".join(["?"] * len(valid_grades))
                    query += f" AND e.grade IN ({placeholders})"
                    params.extend(valid_grades)

            # 4. years (리스트) 또는 year_from / year_to
            if years:
                valid_years = []
                for y in years:
                    if y and y != "전체" and "전체" not in str(y):
                        try:
                            valid_years.append(int(y))
                        except Exception:
                            pass
                if valid_years:
                    placeholders = ", ".join(["?"] * len(valid_years))
                    query += f" AND e.year IN ({placeholders})"
                    params.extend(valid_years)
            else:
                if year_from and year_from != "전체" and "전체" not in str(year_from):
                    try:
                        query += " AND e.year >= ?"
                        params.append(int(year_from))
                    except Exception:
                        pass
                if year_to and year_to != "전체" and "전체" not in str(year_to):
                    try:
                        query += " AND e.year <= ?"
                        params.append(int(year_to))
                    except Exception:
                        pass

            # 5. exam_type (단일 또는 리스트)
            if exam_type:
                raw_types = [exam_type] if isinstance(exam_type, str) else list(exam_type)
                type_clauses = []
                for t in raw_types:
                    if t and t != "전체" and "전체" not in str(t):
                        # UI 라벨 "대학수학능력시험 (수능)" 등이 DB의 "수능"과 매칭되도록 보정
                        if "수능" in t:
                            type_clauses.append("(e.exam_type = '수능' OR e.exam_type LIKE '%수능%' OR ? LIKE '%' || e.exam_type || '%')")
                            params.append(t)
                        elif "6월" in t:
                            type_clauses.append("(e.exam_type LIKE '%6월%')")
                        elif "9월" in t:
                            type_clauses.append("(e.exam_type LIKE '%9월%')")
                        elif "3월" in t:
                            type_clauses.append("(e.exam_type LIKE '%3월%')")
                        elif "4월" in t:
                            type_clauses.append("(e.exam_type LIKE '%4월%')")
                        elif "7월" in t:
                            type_clauses.append("(e.exam_type LIKE '%7월%')")
                        elif "10월" in t:
                            type_clauses.append("(e.exam_type LIKE '%10월%')")
                        else:
                            type_clauses.append("(e.exam_type = ? OR e.exam_type LIKE ? OR ? LIKE '%' || e.exam_type || '%')")
                            params.extend([t, f"%{t}%", t])
                if type_clauses:
                    query += f" AND ({' OR '.join(type_clauses)})"

            # 6. major_chapter / middle_chapter
            if major_chapter and major_chapter != "전체":
                query += " AND q.major_chapter = ?"
                params.append(major_chapter)
            if middle_chapter and middle_chapter != "전체":
                query += " AND q.middle_chapter = ?"
                params.append(middle_chapter)

            # 7. keyword
            if keyword:
                query += " AND (q.question_text LIKE ? OR q.solution_text LIKE ? OR q.major_chapter LIKE ? OR q.middle_chapter LIKE ?)"
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

            query += " ORDER BY e.year DESC, e.month DESC, q.question_num ASC"
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
            for r in rows:
                if 'question_text' in r and r['question_text']:
                    r['question_text'] = normalize_pua_symbols(r['question_text'])
                if 'solution_text' in r and r['solution_text']:
                    r['solution_text'] = normalize_pua_symbols(r['solution_text'])
            return rows

    def get_filter_options(self, subject_name: Optional[str] = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT DISTINCT subject_name FROM questions WHERE subject_name IS NOT NULL AND subject_name != ''")
            subjects = [r[0] for r in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT year FROM exams ORDER BY year DESC")
            years = [r[0] for r in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT grade FROM exams ORDER BY grade ASC")
            grades = [r[0] for r in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT exam_type FROM exams WHERE exam_type IS NOT NULL AND exam_type != ''")
            exam_types = [r[0] for r in cursor.fetchall()]

            portals = [
                "전체",
                "EBSi 국가 교육 포털",
                "한국교육과정평가원 (KICE)",
                "부산광역시교육청 학력개발원",
                "에듀넷 티-클리어 (KERIS)",
                "국가기초학력지원센터 (KICE/KEDI)"
            ]

            major_chapters = []
            middle_chapters = []
            if subject_name and subject_name != "전체":
                cursor.execute("SELECT DISTINCT major_chapter FROM questions WHERE subject_name = ? AND major_chapter IS NOT NULL AND major_chapter != ''", (subject_name,))
                major_chapters = [r[0] for r in cursor.fetchall()]

                cursor.execute("SELECT DISTINCT middle_chapter FROM questions WHERE subject_name = ? AND middle_chapter IS NOT NULL AND middle_chapter != ''", (subject_name,))
                middle_chapters = [r[0] for r in cursor.fetchall()]
            else:
                cursor.execute("SELECT DISTINCT major_chapter FROM questions WHERE major_chapter IS NOT NULL AND major_chapter != ''")
                major_chapters = [r[0] for r in cursor.fetchall()]
                
                cursor.execute("SELECT DISTINCT middle_chapter FROM questions WHERE middle_chapter IS NOT NULL AND middle_chapter != ''")
                middle_chapters = [r[0] for r in cursor.fetchall()]

            return {
                "portals": portals,
                "subjects": subjects,
                "years": years,
                "grades": grades,
                "exam_types": exam_types,
                "major_chapters": major_chapters,
                "middle_chapters": middle_chapters
            }

    def get_question_by_id(self, question_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT q.*, e.year, e.month, e.grade, e.exam_type, e.title as exam_title, e.source_url
            FROM questions q
            JOIN exams e ON q.exam_id = e.id
            WHERE q.id = ?
            """, (question_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_collection_statistics(self) -> Dict[str, Any]:
        """
        공공 출처별, 학년별, 연도별, 시험구분별, 수집 과목별 통계 집계 데이터 반환
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 공공 출처별
            cursor.execute("""
                SELECT COALESCE(e.source_url, '기타') as name, COUNT(q.id) as cnt
                FROM questions q JOIN exams e ON q.exam_id = e.id
                GROUP BY e.source_url ORDER BY cnt DESC
            """)
            by_portal = [dict(r) for r in cursor.fetchall()]

            # 2. 학년별
            cursor.execute("""
                SELECT COALESCE(e.grade, 0) as grade, COUNT(q.id) as cnt
                FROM questions q JOIN exams e ON q.exam_id = e.id
                GROUP BY e.grade ORDER BY e.grade ASC
            """)
            by_grade = [dict(r) for r in cursor.fetchall()]

            # 3. 연도별
            cursor.execute("""
                SELECT COALESCE(e.year, 0) as year, COUNT(q.id) as cnt
                FROM questions q JOIN exams e ON q.exam_id = e.id
                GROUP BY e.year ORDER BY e.year DESC
            """)
            by_year = [dict(r) for r in cursor.fetchall()]

            # 4. 시험 구분별
            cursor.execute("""
                SELECT COALESCE(e.exam_type, '기타') as exam_type, COUNT(q.id) as cnt
                FROM questions q JOIN exams e ON q.exam_id = e.id
                GROUP BY e.exam_type ORDER BY cnt DESC
            """)
            by_exam_type = [dict(r) for r in cursor.fetchall()]

            # 5. 과목별
            cursor.execute("""
                SELECT COALESCE(q.subject_name, '기타') as subject_name, COUNT(q.id) as cnt
                FROM questions q
                GROUP BY q.subject_name ORDER BY cnt DESC
            """)
            by_subject = [dict(r) for r in cursor.fetchall()]

            # 총 문항수
            cursor.execute("SELECT COUNT(*) FROM questions")
            total = cursor.fetchone()[0]

            return {
                "total_questions": total,
                "by_portal": by_portal,
                "by_grade": by_grade,
                "by_year": by_year,
                "by_exam_type": by_exam_type,
                "by_subject": by_subject
            }

    def deduplicate_questions(self) -> Dict[str, int]:
        """
        중복된 문항 지문(question_text)을 제거하여 고유 문항만 보존하고,
        문항이 없는 빈 시험지(exams)를 정리합니다.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM questions")
            initial_count = cursor.fetchone()[0]

            # 0. 시험 구분 명칭 표준화 ('대학수학능력시험 (수능)' -> '수능')
            cursor.execute("UPDATE exams SET exam_type = '수능' WHERE exam_type LIKE '%대학수학능력시험%'")

            # 0-1. 존재하지 않는 exam을 가리키는 고아 문항 삭제 (삭제 도중 다른 수집이 겹치는 등의
            # 이유로 exams만 지워지고 questions는 남는 경우 방지)
            cursor.execute("""
                DELETE FROM questions
                WHERE exam_id NOT IN (SELECT id FROM exams)
            """)

            # 1. 중복 문항 삭제 (고유 question_text 당 1개만 보존)
            cursor.execute("""
                DELETE FROM questions 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM questions 
                    GROUP BY question_text
                )
            """)

            # 2. 문항이 없는 빈 시험지(exams) 삭제
            cursor.execute("""
                DELETE FROM exams 
                WHERE id NOT IN (
                    SELECT DISTINCT exam_id 
                    FROM questions
                )
            """)
            deleted_exams = cursor.rowcount
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM questions")
            remaining_count = cursor.fetchone()[0]

            return {
                "initial_count": initial_count,
                "deleted_count": initial_count - remaining_count,
                "remaining_count": remaining_count,
                "deleted_exams": deleted_exams
            }

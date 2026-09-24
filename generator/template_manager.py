import os
import re
from typing import List, Dict, Any
from generator.hwpx_builder import HwpxBuilder

class TemplateManager:
    """
    시험지/해설지 템플릿 및 일괄 문서 생성 관리자
    - 학생용 문제지 (.hwpx)
    - 교사용 문제지 (.hwpx)
    - 정답 및 해설집 (.hwpx)
    - 실시간 웹 미리보기용 HTML 렌더러 (MathJax 수식 렌더링 지원)
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.hwpx_builder = HwpxBuilder()

    def _normalize_math_for_html(self, text: str) -> str:
        if not text:
            return ""
        # 한컴/평가원 전용 비표준 PUA 특수문자를 표준 유니코드로 치환 (웹 폰트 '네모 엑스' 깨짐 방지)
        pua_replacements = [
            ('\U000f0854', '『'),
            ('\U000f0855', '』'),
            ('\U000f02b1', '㉠'),
            ('\U000f02b2', '㉡'),
            ('\U000f02b3', '㉢'),
            ('\U000f02b4', '㉣'),
            ('\U000f0802', '• '),
            ('\U000f003b', '▼ '),
        ]
        for pua_char, std_char in pua_replacements:
            text = text.replace(pua_char, std_char)

        # \( ... \) 를 $ ... $ 로 통일
        t = re.sub(r'\\\((.*?)\\\)', r'$\1$', text)
        # \[ ... \] 를 $$ ... $$ 로 통일
        t = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', t, flags=re.DOTALL)
        return t

    def generate_all_packages(self, title: str, subtitle: str, questions: List[Dict[str, Any]], header_meta: str = "") -> Dict[str, str]:
        """학생용, 교사용, 해설집 3종 HWPX 문서 일괄 생성"""
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()

        student_file = os.path.join(self.output_dir, f"{clean_title}_[학생용_문제지].hwpx")
        teacher_file = os.path.join(self.output_dir, f"{clean_title}_[교사용_정답포함].hwpx")
        solution_file = os.path.join(self.output_dir, f"{clean_title}_[정답및해설집].hwpx")

        self.hwpx_builder.generate_hwpx(student_file, title, subtitle, questions, mode="student", header_meta=header_meta)
        self.hwpx_builder.generate_hwpx(teacher_file, title, subtitle, questions, mode="teacher", header_meta=header_meta)
        self.hwpx_builder.generate_hwpx(solution_file, title, subtitle, questions, mode="solution", header_meta=header_meta)

        return {
            "student": student_file,
            "teacher": teacher_file,
            "solution": solution_file
        }

    def render_html_preview(self, title: str, subtitle: str, questions: List[Dict[str, Any]], mode: str = "student") -> str:
        """웹 UI에서 바로 볼 수 있는 실시간 2단 시험지 HTML 미리보기 생성 (MathJax 수식 엔진 탑재)"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&display=swap">
          <style>
            .choice-item {{
                margin: 4px 0;
                line-height: 1.6;
                font-size: 15px;
                font-weight: 500;
                color: #0f172a;
                word-break: keep-all;
                white-space: normal;
                margin-left: 5pt;
                padding-left: 10pt;
                text-indent: -10pt;
            }}
            .choice-row {{
                display: flex;
                flex-direction: row;
                justify-content: space-between;
                gap: 8px;
                margin-top: 8px;
                font-size: 15px;
                font-weight: 500;
                color: #0f172a;
                word-break: keep-all;
            }}
            .choice-row span {{
                white-space: nowrap !important;
                flex-shrink: 0;
                display: inline-block;
            }}
          </style>
          <script>
          window.MathJax = {{
            tex: {{
              inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
              displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
            }},
            svg: {{
              fontCache: 'global'
            }}
          }};
          </script>
          <script type="text/javascript" id="MathJax-script" async
            src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
          </script>
        </head>
        <body style="margin:0; padding:0; background: transparent;">
        <div style="background-color: #f8fafc; padding: 22px; border-radius: 12px; font-family: 'Noto Sans KR', 'Pretendard', 'Malgun Gothic', sans-serif; color: #1e293b; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="text-align: center; border-bottom: 2px solid #3b82f6; padding-bottom: 14px; margin-bottom: 20px;">
                <h2 style="margin: 0; color: #0f172a; font-size: 24px; font-weight: 800;">{title}</h2>
                <div style="margin-top: 6px; color: #64748b; font-size: 14.5px; font-weight: 600;">{subtitle}</div>
                <!-- (총 문항 수 / 배점 합계 / 모드 요약 바는 화면 정리를 위해 주석 처리)
                <div style="margin-top: 10px; display: flex; justify-content: space-around; background: #eff6ff; padding: 8px; border-radius: 6px; font-size: 14px; color: #1e40af;">
                    <span>총 문항 수: <b>{len(questions)}문항</b></span>
                    <span>배점 합계: <b>{sum(q.get('score', 2) for q in questions)}점</b></span>
                    <span>모드: <b>{'학생용 문제지' if mode=='student' else ('교사용 (정답/배점 표기)' if mode=='teacher' else '정답 및 해설집')}</b></span>
                </div>
                -->
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        """

        current_chapter = ""
        last_jimum_sig = ""
        for idx, q in enumerate(questions, start=1):
            q_major = q.get("major_chapter", "")
            q_middle = q.get("middle_chapter", "")
            q_score = q.get("score", 2)
            q_text = q.get("question_text", "")
            q_ans = str(q.get("answer", "") or "")
            q_rate = str(q.get("correct_rate", "") or "")
            q_sol = q.get("solution_text", "")
            q_source = f"{q.get('year', '')}년 {q.get('exam_type', '')} {q.get('question_num', '')}번"

            # 유의미한 단원 분류가 있는 경우에만 문항 상단에 단원 태그 노출 (국어, 영어 등 미분류 과목의 '단원 미분류'는 숨김)
            has_valid_chapter = bool(q_major and q_major != "단원 미분류") or bool(q_middle and q_middle != "단원 미분류")
            chapter_str = ""
            if has_valid_chapter:
                parts = [p for p in [q_major, q_middle] if p and p != "단원 미분류"]
                chapter_str = " &gt; ".join(parts)
            chapter_tag = f"<div style='font-size:12.5px; color:#1d4ed8; font-weight:700; background:#dbeafe; padding:3px 8px; border-radius:5px; margin-bottom:8px; display:inline-block;'>{chapter_str}</div>" if chapter_str else ""

            if mode == "solution":
                sol_content = self._normalize_math_for_html(q_sol or "해설이 제공되지 않는 문항입니다.").replace("\n", "<br/>")
                html += f"""
                <div style="background: #ffffff; padding: 18px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                    {chapter_tag}
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px dashed #cbd5e1; padding-bottom: 6px;">
                        <span style="font-size: 16px; font-weight: 800; color: #1e3a8a;">[{idx:02d}번 해설]</span>
                        <span style="font-size: 13px; color: #b91c1c; font-weight: 700;">정답: {q_ans}번</span>
                        <span style="font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #64748b;">{q_source}</span>
                    </div>
                    <div style="font-size: 15px; font-weight: 500; line-height: 1.7; color: #0f172a;">
                        {sol_content}
                    </div>
                </div>
                """
            else:
                # 학생용 / 교사용
                parsed = self.hwpx_builder._parse_question_text(
                    text=q_text,
                    score=q_score,
                    idx=idx,
                    mode=mode,
                    ans=q_ans,
                    rate=q_rate,
                    source=q_source
                )

                # 1) 헤더 발문 HTML
                header_html_list = []
                for h_idx, h_line in enumerate(parsed["header_lines"]):
                    norm_line = self._normalize_math_for_html(h_line)
                    if h_idx == 0:
                        header_html_list.append(f"<div style='font-weight: 700; color: #0f172a; margin-bottom: 6px; font-size: 15px; text-indent: -5pt; padding-left: 5pt;'>{norm_line}</div>")
                    else:
                        header_html_list.append(f"<div style='margin-bottom: 6px; text-indent: -5pt; padding-left: 5pt;'>{norm_line}</div>")
                header_html = "".join(header_html_list)

                # 공통 지문(예: [1~3], [4~9])은 첫 번째 문항에만 표시하고, 후속 문항(Q2, Q3 등)에서는 중복 표시를 방지
                current_jimum_sig = parsed.get("jimum_sig", "")
                should_render_jimum = bool((parsed.get("jimum_lines") or parsed.get("jimum_header")) and (not current_jimum_sig or current_jimum_sig != last_jimum_sig))
                if parsed.get("jimum_lines") or parsed.get("jimum_header"):
                    last_jimum_sig = current_jimum_sig
                # 2) 지문 및 보기 상자 분리 렌더링
                # (지문 안내 헤더 [ ~ ] 다음 글을 읽고 물음에 답하시오 는 네모 박스 위 일반 텍스트로 배치)
                jimum_header_html = ""
                jimum_box_html = ""
                if should_render_jimum and (parsed.get("jimum_lines") or parsed.get("jimum_header")):
                    if parsed.get("jimum_header"):
                        norm_jh = self._normalize_math_for_html(parsed["jimum_header"])
                        jimum_header_html = f"<div style='font-weight: 700; color: #0f172a; margin-bottom: 8px; font-size: 14.5px;'>{norm_jh}</div>"

                    if parsed.get("jimum_lines"):
                        j_paragraphs = []
                        for b in parsed["jimum_lines"]:
                            norm_p = self._normalize_math_for_html(b)
                            if re.match(r'^\([가-하A-Za-z0-9]\)$', b):
                                j_paragraphs.append(f"<div style='font-weight: 700; color: #1e40af; margin: 6px 0 4px 0;'>{norm_p}</div>")
                            else:
                                j_paragraphs.append(f"<div style='margin-bottom: 6px; text-align: justify;'>{norm_p}</div>")
                        j_inner = "".join(j_paragraphs)
                        jimum_box_html = f"""<div style="border: 1.5px solid #334155; border-radius: 4px; padding: 12px 16px; margin: 0 0 14px 0; background: #fafafa; font-size: 14.5px; font-weight: 500; line-height: 1.75; word-break: keep-all; color: #0f172a;">{j_inner}</div>"""

                bogi_box_html = ""
                if parsed.get("bogi_lines"):
                    b_lines = parsed["bogi_lines"]
                    title_html = ""
                    content_start_idx = 0
                    if b_lines and "< 보 기 >" in b_lines[0]:
                        title_html = "<div style='text-align: center; font-weight: 700; margin-bottom: 10px; letter-spacing: 2px; color: #0f172a;'>&lt; 보 기 &gt;</div>"
                        content_start_idx = 1
                    
                    b_paragraphs = []
                    for b in b_lines[content_start_idx:]:
                        norm_p = self._normalize_math_for_html(b)
                        b_paragraphs.append(f"<div style='margin-bottom: 4px; text-align: justify;'>{norm_p}</div>")
                    b_inner = "".join(b_paragraphs)
                    bogi_box_html = f"""<div style="border: 1.5px solid #334155; border-radius: 4px; padding: 12px 16px; margin: 12px 0; background: #fafafa; font-size: 14.5px; font-weight: 500; line-height: 1.75; word-break: keep-all; color: #0f172a;">{title_html}{b_inner}</div>"""

                # 3) 후속 질문 발문 HTML
                footer_html = ""
                if parsed["footer_lines"]:
                    footer_inner = "".join([f"<div style='font-weight: 600; color: #0f172a; margin: 8px 0 6px 0; font-size: 14.5px;'>{self._normalize_math_for_html(f)}</div>" for f in parsed["footer_lines"]])
                    footer_html = footer_inner

                # 4) 선택지 렌더링 (중간 줄바꿈 방지 및 가독성 최적화)
                choices_html = ""
                if parsed["choice_items"]:
                    if parsed["is_multiline_choice"]:
                        choices_inner = "".join([f"<div class='choice-item'>{self._normalize_math_for_html(c)}</div>" for c in parsed["choice_items"]])
                        choices_html = f"<div style='margin-top: 10px; padding-left: 4px; display: flex; flex-direction: column; gap: 4px;'>{choices_inner}</div>"
                    else:
                        choices_inner = "".join([f"<span style='white-space: nowrap; flex-shrink: 0;'>{self._normalize_math_for_html(c)}</span>" for c in parsed["choice_items"]])
                        choices_html = f"<div class='choice-row' style='padding-left: 4px;'>{choices_inner}</div>"

                teacher_header = ""
                if mode == "teacher" and q_ans and q_ans != "미확인":
                    rate_str = f" (정답률: {q_rate}%)" if q_rate and q_rate != "None" and q_rate != "%" else ""
                    teacher_header = f"<span style='background:#fee2e2; color:#b91c1c; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:700;'>정답: {q_ans}번{rate_str}</span>"

                # 교사용: 해설이 수집된 문항만 문항 아래에 해설을 붙여 보여준다.
                teacher_sol_html = ""
                if mode == "teacher" and str(q_sol or "").strip():
                    _sol_body = self._normalize_math_for_html(str(q_sol)).replace(chr(10), "<br/>")
                    teacher_sol_html = (
                        "<div style='margin-top: 12px; padding: 10px 12px; background: #f0fdf4; border-left: 3px solid #16a34a; "
                        "border-radius: 4px; font-size: 13px; line-height: 1.7; color: #14532d;'>"
                        f"<b>▶ 해설</b><br/>{_sol_body}</div>"
                    )

                html += f"""
                <div style="background: #ffffff; padding: 18px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        {chapter_tag}
                        <div>
                            {teacher_header}
                            <span style="font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #64748b; margin-left: 4px;">{q_source}</span>
                        </div>
                    </div>
                    <div style="font-size: 15px; font-weight: 500; line-height: 1.7; color: #0f172a;">
                        {jimum_header_html}
                        {jimum_box_html}
                        {header_html}
                        {bogi_box_html}
                        {footer_html}
                        {choices_html}
                        {teacher_sol_html}
                    </div>
                </div>
                """

        html += """
            </div>
        </div>
        <div id="preview-error-log" style="display:none; margin-top:20px; padding:12px; background:#fee2e2; border:1px solid #ef4444; border-radius:6px; color:#b91c1c; font-size:13px; font-family:monospace; white-space:pre-wrap;"></div>
        <script>
        window.onerror = function(msg, url, lineNo, columnNo, error) {
            console.error("Preview Render Error:", msg, "at line:", lineNo, error);
            var errBox = document.getElementById("preview-error-log");
            if (errBox) {
                errBox.style.display = "block";
                errBox.innerText += "[렌더링 오류 감지] " + msg + " (라인 " + lineNo + ")\n";
            }
            return false;
        };
        try {
            if (window.MathJax && window.MathJax.typesetPromise) {
                window.MathJax.typesetPromise().catch(function (err) {
                    console.warn("MathJax typeset failed:", err.message);
                });
            }
        } catch(e) {
            console.warn("MathJax exec error:", e);
        }
        </script>
        </body>
        </html>
        """
        return html


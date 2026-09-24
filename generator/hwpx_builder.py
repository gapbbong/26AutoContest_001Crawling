import os
import re
import zipfile
import xml.sax.saxutils as saxutils
from typing import List, Dict, Any, Optional

class HwpxBuilder:
    """
    한글(HWPX / KS X 6101) 표준 문서 생성 엔진
    - 한컴오피스 한글 2020/2022/2024 및 공공기관 뷰어 완벽 호환
    - 학교 표준 2단 시험지 레이아웃 (학생용, 교사용, 해설집) 자동 조판
    """

    def __init__(self):
        pass

    def _escape(self, text: str) -> str:
        if not text:
            return ""
        # [1～3] 같은 지문 범위 표기의 물결표를 화면에서 이상하게 보이는 전각(～)/연산자(∼) 대신 표준 반각 물결표(~)로 통일
        normalized = str(text).replace('～', '~').replace('∼', '~')
        # XML 특수문자 이스케이프 및 XML 1.0 비허용 제어문자 제거
        escaped = saxutils.escape(normalized)
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]', '', escaped)

    def _create_mimetype(self, zf: zipfile.ZipFile):
        # KS X 6101 스펙: mimetype은 압축 없이 첫 번째 엔트리에 저장되어야 함
        zf.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)

    def _create_version_xml(self, zf: zipfile.ZipFile):
        # 한컴 공식 규격: version.xml은 ZIP_STORED(무압축)으로 저장됨
        # 하위 버전 한글(2018/2020 등)에서도 '상위 버전에서 작성한 문서입니다' 팝업이 뜨지 않도록 광범위 호환 버전(5.0.0.0)으로 설정
        xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" major="5" minor="0" micro="0" buildNumber="0" os="1" xmlVersion="1.0" application="Hancom Office Hangul" appVersion="10, 0, 0, 11131 WIN32LEWindows_10"/>'
        zf.writestr("version.xml", xml_content, compress_type=zipfile.ZIP_STORED)

    def _create_settings_xml(self, zf: zipfile.ZipFile):
        xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"><ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>'
        zf.writestr("settings.xml", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _create_preview_image(self, zf: zipfile.ZipFile):
        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_prv_image.png")
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            zf.writestr("Preview/PrvImage.png", img_bytes, compress_type=zipfile.ZIP_STORED)

    def _create_container_xml(self, zf: zipfile.ZipFile):
        xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"><ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/><ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/><ocf:rootfile full-path="META-INF/container.rdf" media-type="application/rdf+xml"/></ocf:rootfiles></ocf:container>'
        zf.writestr("META-INF/container.xml", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _create_manifest_xml(self, zf: zipfile.ZipFile):
        xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
        zf.writestr("META-INF/manifest.xml", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _create_container_rdf(self, zf: zipfile.ZipFile):
        xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about=""><ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#" rdf:resource="Contents/header.xml"/></rdf:Description><rdf:Description rdf:about="Contents/header.xml"><rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#HeaderFile"/></rdf:Description><rdf:Description rdf:about=""><ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#" rdf:resource="Contents/section0.xml"/></rdf:Description><rdf:Description rdf:about="Contents/section0.xml"><rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#SectionFile"/></rdf:Description><rdf:Description rdf:about=""><rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#Document"/></rdf:Description></rdf:RDF>'
        zf.writestr("META-INF/container.rdf", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _create_preview_text(self, zf: zipfile.ZipFile, title: str, subtitle: str):
        prv_content = f"{title}\r\n{subtitle}\r\n"
        zf.writestr("Preview/PrvText.txt", prv_content.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)

    def _create_content_hpf(self, zf: zipfile.ZipFile, title: str):
        xml_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><opf:package xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf/" xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0" version="" unique-identifier="" id=""><opf:metadata><opf:title>{self._escape(title)}</opf:title><opf:language>ko</opf:language><opf:meta name="creator" content="text">Busan Edu Auto</opf:meta></opf:metadata><opf:manifest><opf:item id="header" href="Contents/header.xml" media-type="application/xml"/><opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/><opf:item id="settings" href="settings.xml" media-type="application/xml"/></opf:manifest><opf:spine><opf:itemref idref="header" linear="yes"/><opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>"""
        zf.writestr("Contents/content.hpf", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _create_header_xml(self, zf: zipfile.ZipFile):
        header_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_header.xml")
        if os.path.exists(header_path):
            with open(header_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
        else:
            xml_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="1.5" secCnt="1">
  <hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>
</hh:head>"""
        zf.writestr("Contents/header.xml", xml_content, compress_type=zipfile.ZIP_DEFLATED)

    def _normalize_latex_for_hwpx(self, text: str) -> str:
        """
        LaTeX 수식 표현($...$, $$...$$, \\le, \\sqrt 등)을 한글/HWPX 표준 유니코드 수식 타이포그래피로 자동 변환
        - 한컴오피스 뷰어 및 출력 시 LaTeX 원시 코드가 깨져서 노출되는 문제를 완벽 방지
        """
        if not text:
            return ""

        replacements = [
            (r'\\le\b|\\leq\b', '≤'),
            (r'\\ge\b|\\geq\b', '≥'),
            (r'\\ne\b|\\neq\b', '≠'),
            (r'\\pm\b', '±'),
            (r'\\times\b', '×'),
            (r'\\cdot\b', '·'),
            (r'\\div\b', '÷'),
            (r'\\alpha\b', 'α'),
            (r'\\beta\b', 'β'),
            (r'\\theta\b', 'θ'),
            (r'\\pi\b', 'π'),
            (r'\\sigma\b', 'σ'),
            (r'\\omega\b', 'ω'),
            (r'\\in\b', '∈'),
            (r'\\notin\b', '∉'),
            (r'\\subset\b', '⊂'),
            (r'\\subseteq\b', '⊆'),
            (r'\\cap\b', '∩'),
            (r'\\cup\b', '∪'),
            (r'\\emptyset\b', '∅'),
            (r'\\infty\b', '∞'),
            (r'\\to\b|\\rightarrow\b', '→'),
            (r'\\implies\b', '⇒'),
            (r'\\iff\b', '⇔'),
            (r'\\approx\b', '≈'),
            (r'\\equiv\b', '≡'),
            (r'\\{', '{'),
            (r'\\}', '}'),
            (r'\\sin\b', 'sin'),
            (r'\\cos\b', 'cos'),
            (r'\\tan\b', 'tan'),
            (r'\\log\b', 'log'),
            (r'\\ln\b', 'ln'),
        ]

        # 한컴/평가원 전용 비표준 PUA 특수문자를 표준 유니코드로 치환
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

        t = text
        t = re.sub(r'\\text\{([^}]*)\}', r'\1', t)
        t = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', t)

        for pattern, repl in replacements:
            t = re.sub(pattern, repl, t)

        # \sqrt[3]{...} -> ∛...
        t = re.sub(r'\\sqrt\[3\]\{([^}]*)\}', r'∛\1', t)
        # \sqrt{...} -> √...
        t = re.sub(r'\\sqrt\{([^}]*)\}', r'√\1', t)
        
        # \frac{a}{b} -> a/b
        t = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1/\2', t)

        # \lim_{x \to a} -> lim(x→a)
        t = re.sub(r'\\lim_\{([^}]*)\}', r'lim(\1)', t)

        # 위첨자 변환 (^2 -> ², ^3 -> ³, ^n -> ⁿ 등)
        sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '+': '⁺', '-': '⁻', 'n': 'ⁿ', 'x': 'ˣ', 'y': 'ʸ'}
        def replace_sup(match):
            content = match.group(1) or match.group(2)
            if len(content) == 1 and content in sup_map:
                return sup_map[content]
            elif content == "-1":
                return "⁻¹"
            return f"^{content}"

        t = re.sub(r'\^\{([^}]+)\}|\^([0-9nxy+-])', replace_sup, t)

        # 아래첨자 변환 (_1 -> ₁, _10 -> ₁₀ 등)
        sub_map = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉', 'n': 'ₙ', 'k': 'ₖ', 'i': 'ᵢ'}
        def replace_sub(match):
            content = match.group(1) or match.group(2)
            if len(content) == 1 and content in sub_map:
                return sub_map[content]
            elif content.isdigit() and len(content) <= 3:
                return "".join(sub_map.get(c, c) for c in content)
            return f"_{content}"

        t = re.sub(r'\_\{([^}]+)\}|\_([0-9nki])', replace_sub, t)

        # 수식 구분자($, $$, \(, \), \[, \]) 제거
        t = re.sub(r'\$\$(.*?)\$\$', r'\1', t, flags=re.DOTALL)
        t = re.sub(r'\$(.*?)\$', r'\1', t)
        t = re.sub(r'\\\[(.*?)\\\]', r'\1', t, flags=re.DOTALL)
        t = re.sub(r'\\\((.*?)\\\)', r'\1', t)

        # 연속 공백 축소
        t = re.sub(r'[ \t]+', ' ', t)
        return t.strip()

    def _normalize_box_paragraphs(self, lines: List[str]) -> List[str]:
        """
        PDF 추출 시 2단 너비 제한으로 인해 문장 도중에 강제 줄바꿈된 행들을
        의미 단위(문단, 헤더, 보기 기호 등)의 자연스러운 한 문단/문장 단위로 자동 결합(Unwrap)
        - '[1~3]', '<보 기>', '(가)', '(나)' 등 고유 구분자는 독립 행으로 보존
        - 한 문단 내의 인위적인 강제 개행을 제거하여 실전 시험지처럼 미려한 줄바꿈 보장
        """
        if not lines:
            return []

        result = []
        curr = []

        def flush():
            nonlocal curr
            if curr:
                result.append(" ".join(curr))
                curr = []

        for raw_line in lines:
            s = raw_line.strip()
            if not s:
                flush()
                continue

            # 1. 지문 안내 헤더: [1~3] 다음 글을 읽고 물음에 답하시오.
            if re.match(r'^\[\d+[\s～~-]+\d+\]', s):
                flush()
                result.append(s)
                continue

            # 2. 보기 헤더: < 보 기 >
            if re.match(r'^[<\[]\s*보\s*기\s*[>\]]\s*$', s):
                flush()
                result.append("< 보 기 >")
                continue

            # 3. 단락 구분 기호: (가), (나), (다)
            if re.match(r'^\([가-하A-Za-z0-9]\)$', s):
                flush()
                result.append(s)
                continue

            # 4. 그림/자료/문단 블록 헤더: <그림>, [표 1], <조건>, [작문 상황], [학생의 초고], [앞부분의 줄거리] 등
            if (re.match(r'^[<\[][^>\]]+[>\]]$', s) and len(s) <= 25) or re.match(r'^[<\[]\s*(그림|도표|표|조건|참고자료|자료|작문\s*상황|학생의\s*초고|초고)\s*\d*\s*[>\]]', s):
                flush()
                result.append(s)
                continue

            # 5. 보기 내 항목 기호: ㄱ., ㄴ., 1), 2), ① 등
            if re.match(r'^[ㄱ-ㅎ]\.|\([ㄱ-ㅎ]\)|^[0-9]+\)|\b[A-Z]\.|\b[a-z]\.', s):
                flush()
                curr.append(s)
                continue

            curr.append(s)

        flush()
        return result

    def _parse_question_text(self, text: str, score: int, idx: int, mode: str = "student",
                             ans: str = "", rate: str = "", source: str = "") -> Dict[str, Any]:
        """
        문항 텍스트를 질문 헤더(Header), 지문/보기 상자(Box), 후속 발문(Footer), 선택지(Choices)로 구조화 분리
        - [지문] 텍스트 태그는 100% 제거하고 본문만 추출하여 실전 시험지 네모 상자 안에 배치
        - 질문 번호(1., 2.)는 첫 번째 헤더 문장 시작에 배치
        - 배점([2점], [3점])은 후속 발문 끝(없으면 헤더 끝)에 배치
        - 선택지(①~⑤)는 줄바꿈/너비에 따라 자동 1줄 또는 다단 분할
        - 수식은 HWPX 타이포그래피로 자동 변환
        """
        # 시험지 하단 안내문/확인 사항 (* 확인 사항, ◦답안지의 해당란에..., ◦이어서, ｢선택과목...｣, 저작권 문구 등) 제거
        text = re.sub(r'(?:\*|\s)*확인\s*사항[\s\S]*$', '', text).strip()
        text = re.sub(r'◦\s*답안지의\s*해당란에[\s\S]*$', '', text).strip()
        text = re.sub(r'◦\s*이어서,\s*[｢\[][\s\S]*$', '', text).strip()
        text = re.sub(r'이 문제지에 관한 저작권은 한국교육과정평가원에 있습니다\.?', '', text).strip()

        match = re.search(r'(?:\n|\s)*(①[\s\S]*)', text)
        if match:
            prompt_part = text[:match.start()].strip()
            choices_part = match.group(1).strip()
        else:
            prompt_part = text
            choices_part = ""

        choice_items = []
        if choices_part:
            raw_choices = re.split(r'([①②③④⑤])', choices_part)
            current_num = None
            for item in raw_choices:
                item = item.strip()
                if not item:
                    continue
                if item in ('①', '②', '③', '④', '⑤'):
                    current_num = item
                elif current_num:
                    clean_choice = self._normalize_latex_for_hwpx(item)
                    # 선택지 내부의 PDF 추출 인위적 강제 개행 및 공백 정규화 (1개 선택지가 여러 줄로 쪼개지지 않도록 Unwrap)
                    clean_choice = " ".join(clean_choice.split())
                    # 선택지 끝에 남아있을 수 있는 불필요한 시험지 확인 사항 / 저작권 / 다음 지문 누출 / 단 라벨([A] [B]) 찌꺼기 제거
                    clean_choice = re.sub(r'(?:\*|\s)*확인\s*사항[\s\S]*$', '', clean_choice).strip()
                    clean_choice = re.sub(r'◦\s*답안지의\s*해당란에[\s\S]*$', '', clean_choice).strip()
                    clean_choice = re.sub(r'◦\s*이어서,\s*[｢\[][\s\S]*$', '', clean_choice).strip()
                    clean_choice = re.sub(r'\[\d+[\s～~-]+\d+\].*$', '', clean_choice, flags=re.DOTALL).strip()
                    clean_choice = re.sub(r'\n+\s*\d+\s*\n+\s*(?:고[1-3]|\([^\)]+\)|[가-힣]+영역)[\s\S]*$', '', clean_choice).strip()
                    # 교사용 모드에서는 정답 번호를 속이 찬 원문자(❶~❺)로 강조 표시 ('[정답]' 텍스트 레이블은 표시하지 않음)
                    num_display = current_num
                    if mode == "teacher" and ans and ans != "미확인":
                        circle_map = {'1': '①', '2': '②', '3': '③', '4': '④', '5': '⑤'}
                        filled_map = {'1': '❶', '2': '❷', '3': '❸', '4': '❹', '5': '❺',
                                      '①': '❶', '②': '❷', '③': '❸', '④': '❹', '⑤': '❺'}
                        target_ans_sym = circle_map.get(str(ans).strip(), str(ans).strip())
                        if current_num == target_ans_sym:
                            num_display = filled_map.get(current_num, current_num)

                    choice_items.append(f"{num_display} {clean_choice}")
                    current_num = None

        # 선택지 레이아웃 판별:
        # 단일행(5개 한 줄): 모든 선택지가 5자 이하이고 전체 합이 24자 이하일 때만 (예: 숫자, 단답형 보기)
        # 문장형 또는 6자 이상 선택지가 1개라도 포함된 경우 100% 개별 행으로 안전하게 줄바꿈 배치
        is_multiline_choice = any(len(c) > 5 for c in choice_items) or len("   ".join(choice_items)) > 24

        raw_lines = [l.strip() for l in prompt_part.split("\n") if l.strip()]
        normalized_raw = [self._normalize_latex_for_hwpx(l) for l in raw_lines if l.strip()]

        # 1. 텍스트 선두나 내부에 포함된 시험 출처 헤더([2025학년도 국어...]), 저작권 안내문 및 페이지 하단 과목명 태그 제거
        filtered_raw = []
        for l in normalized_raw:
            if re.match(r'^\[\d{4}학년도[^\]]*\d+번\]', l):
                continue
            if "이 문제지에 관한 저작권은" in l or "한국교육과정평가원에 있습니다" in l:
                continue
            if re.match(r'^\((화법과\s*작문|언어와\s*매체|독서|문학)\)$', l) or l in ('화법과 작문', '언어와 매체', '독서', '문학'):
                continue
            filtered_raw.append(l)

        header_lines = []
        jimum_lines = []
        bogi_lines = []
        footer_lines = []

        # 단독 보기 헤더만 매칭 (<보 기>, <보기>, [보 기], [보기])
        # 주의: "<보기>를 참고하여 ... 것은?" 같은 질문 발문 문장은 bogi_header가 아님!
        bogi_pattern = r'^[<\[]\s*보\s*기\s*[>\]]\s*$'
        jimum_pattern = r'\[지문\]|^\s*\[지문'

        has_jimum = any(re.search(jimum_pattern, l) for l in filtered_raw)
        has_bogi = any(re.match(bogi_pattern, l) for l in filtered_raw)

        bogi_idx = -1
        for i, l in enumerate(filtered_raw):
            if re.match(bogi_pattern, l):
                bogi_idx = i
                break

        prompt_lines = []
        if bogi_idx != -1:
            bogi_raw = filtered_raw[bogi_idx:]
            bogi_lines = [bogi_raw[0]]
            for l in bogi_raw[1:]:
                bogi_lines.append(l)

            pre_bogi = filtered_raw[:bogi_idx]
            p_start = len(pre_bogi)
            for i in range(len(pre_bogi) - 1, -1, -1):
                line = pre_bogi[i]
                if re.match(r'^\[\d+[\s～~-]+\d+\]', line) or line == '[지문]' or re.match(r'^-.*-$', line) or line.startswith('*'):
                    break
                is_prompt_end = bool(re.search(r'(것은\?|않은 것은\?|옳은 것은\?|옳지 않은 것은\?|고른 것은\?|답하시오\.)(\s*\[\d점\])?$', line))
                if is_prompt_end:
                    p_start = i
                elif p_start < len(pre_bogi):
                    if not line.endswith('.') or line.endswith('때,'):
                        p_start = i
                    else:
                        break

            prompt_lines = pre_bogi[p_start:]
            jimum_raw = pre_bogi[:p_start]
            for l in jimum_raw:
                cleaned = re.sub(r'^\[지문\]\s*', '', l).strip()
                if cleaned:
                    jimum_lines.append(cleaned)
        else:
            p_start = len(filtered_raw)
            for i in range(len(filtered_raw) - 1, -1, -1):
                line = filtered_raw[i]
                if re.match(r'^\[\d+[\s～~-]+\d+\]', line) or line == '[지문]' or re.match(r'^-.*-$', line) or line.startswith('*'):
                    break
                is_prompt_end = bool(re.search(r'(것은\?|않은 것은\?|옳은 것은\?|옳지 않은 것은\?|고른 것은\?|답하시오\.)(\s*\[\d점\])?$', line))
                if is_prompt_end:
                    p_start = i
                elif p_start < len(filtered_raw):
                    if not line.endswith('.') or line.endswith('때,'):
                        p_start = i
                    else:
                        break

            prompt_lines = filtered_raw[p_start:]
            jimum_raw = filtered_raw[:p_start]
            for l in jimum_raw:
                cleaned = re.sub(r'^\[지문\]\s*', '', l).strip()
                if cleaned:
                    jimum_lines.append(cleaned)

        footer_lines = prompt_lines

        # 질문 발문 줄바꿈 정규화 (Unwrap): 좁은 폭으로 인해 쪼개진 발문 문장들을 자연스럽게 한 문장으로 결합
        clean_prompt = " ".join(footer_lines).strip()
        clean_prompt = re.sub(r'\[[2-4]점\]\s*$', '', clean_prompt).strip()
        if not clean_prompt:
            clean_prompt = "다음 물음에 답하시오."

        # 문항 번호 다음에 곧바로 질문이 나오도록 구성 (배점만 끝에 표기)
        # 이미 텍스트 선두에 1., 2. 등의 번호가 포함되어 있다면 제거 후 현재 idx로 일관성 있게 부여
        clean_prompt = re.sub(r'^\d+\.\s*', '', clean_prompt).strip()
        q_heading = f"{idx}. {clean_prompt}"
        if not re.search(r'\[[2-4]점\]\s*$', q_heading):
            q_heading += f" [{score}점]"

        if mode == "solution":
            header_lines = [f"[{idx:02d}번 해설] 정답: {ans}번 ({source})"]
        else:
            header_lines = [q_heading]
        footer_lines = []

        # 공통 지문 식별용 시그니처 (헤더 [1~3], [4~9] 등 또는 지문 첫 머리글)
        jimum_sig = ""
        if jimum_lines:
            m_head = re.search(r'\[\d+[\s～~-]+\d+\]', jimum_lines[0])
            if m_head:
                jimum_sig = m_head.group(0)
            else:
                jimum_sig = " ".join(jimum_lines[:2])

        # [ ~ ] 다음 글을 읽고 물음에 답하시오 와 같은 지문 헤더는 박스 본문 정규화 전 정확히 분리 추출
        jimum_header = ""
        header_parts = []
        if jimum_lines and re.match(r'^\[\d+[\s～~-]+\d+\]', jimum_lines[0].strip()):
            header_parts.append(jimum_lines.pop(0).strip())
            while jimum_lines:
                if '답하시오' in header_parts[-1]:
                    break
                # 다음 행이 [작문 상황]이나 (가) 등 새로운 블록의 시작이면 헤더 분할 중단
                if re.match(r'^\[[^\]]+\]', jimum_lines[0].strip()) or re.match(r'^\([가-하A-Za-z0-9]\)', jimum_lines[0].strip()):
                    break
                header_parts.append(jimum_lines.pop(0).strip())
            jimum_header = " ".join(header_parts).strip()

        # PDF 추출 시 너비 제한으로 문장 중간에 강제 줄바꿈된 행들을 자연스러운 한 문단/문장 단위로 자동 정규화
        jimum_lines = self._normalize_box_paragraphs(jimum_lines)
        bogi_lines = self._normalize_box_paragraphs(bogi_lines)

        # 하위 호환성을 위해 box_lines도 제공 (지문 + 보기)
        box_lines = []
        if jimum_lines:
            box_lines.extend(jimum_lines)
        if bogi_lines:
            box_lines.extend(bogi_lines)

        return {
            "header_lines": header_lines,
            "jimum_header": jimum_header,
            "jimum_lines": jimum_lines,
            "bogi_lines": bogi_lines,
            "jimum_sig": jimum_sig,
            "box_lines": box_lines,
            "footer_lines": footer_lines,
            "choice_items": choice_items,
            "is_multiline_choice": is_multiline_choice
        }

    def _build_section_xml(self, title: str, subtitle: str, questions: List[Dict[str, Any]], mode: str = "student", header_meta: str = "") -> str:
        """
        mode:
          - "student": 학생용 문제지 (질문지 끝 배점 표기, 줄바꿈 방지 선택지, 지문 네모 상자 조판)
          - "teacher": 교사용 문제지 (질문지 끝 배점 및 정답/정답률 표기)
          - "solution": 정답 및 상세 해설집
        """
        p_id = 1
        paras = []

        # 교사용 모드: 타이틀 맨 앞 또는 타이틀에 [교사용] 포함
        display_title = f"[교사용] {title}" if mode == "teacher" else title

        # 공공출처 동적 파악 (EBSi, 한국교육과정평가원, 시도교육청 등)
        source_candidates = set()
        for q in questions:
            src_url = q.get("source_url", "")
            exam_t = q.get("exam_type", "")
            if "ebs" in src_url.lower() or "ebsi" in src_url.lower() or "EBS" in src_url:
                source_candidates.add("EBS")
            if "kice" in src_url.lower() or "평가원" in src_url or "수능" in exam_t or "모의평가" in exam_t:
                source_candidates.add("한국교육과정평가원")
            if "pen.go.kr" in src_url or "교육청" in src_url or "전국연합" in exam_t or "학력평가" in exam_t:
                source_candidates.add("시·도교육청")

        if "한국교육과정평가원" in source_candidates and "EBS" in source_candidates:
            public_source = "한국교육과정평가원 및 EBS"
        elif "한국교육과정평가원" in source_candidates:
            public_source = "한국교육과정평가원"
        elif "시·도교육청" in source_candidates and "EBS" in source_candidates:
            public_source = "전국시도교육청 및 EBS"
        elif "시·도교육청" in source_candidates:
            public_source = "전국시도교육청"
        elif "EBS" in source_candidates:
            public_source = "EBS"
        else:
            public_source = "한국교육과정평가원 및 EBS"

        copyright_text = f"이 문제지에 관한 저작권은 {public_source}에 있습니다."

        # 머리말(페이지 상단): 학년도/학년/시험구분/과목/문항수 좌측 정렬 안내 (전달된 경우에만 출력)
        header_ctrl_xml = ""
        if header_meta:
            header_ctrl_xml = f"""
    <hp:ctrl>
      <hp:header id="" applyPage="BOTH">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="900010" paraPrIDRef="11" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
            <hp:run charPrIDRef="3"><hp:t>{self._escape(header_meta)}</hp:t></hp:run>
          </hp:p>
          <hp:p id="900011" paraPrIDRef="11" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
            <hp:run charPrIDRef="3"><hp:t></hp:t></hp:run>
          </hp:p>
          <hp:p id="900012" paraPrIDRef="11" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
            <hp:run charPrIDRef="3"><hp:t></hp:t></hp:run>
          </hp:p>
        </hp:subList>
      </hp:header>
    </hp:ctrl>"""

        # 1. 첫 번째 문단: secPr (2단 레이아웃 및 여백 설정), 머리말/꼬리말(저작권 문구), 하단 가운데 쪽 번호(pageNum) 포함 + 단일 타이틀 출력
        first_p = f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="1">
    <hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="1" memoShapeIDRef="1" textVerticalWidthHead="0" masterPageCnt="0">
      <hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>
      <hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>
      <hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>
      <hp:lineNumberShape restartType="0" countBy="0" distance="0" startNumber="0"/>
      <hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY">
        <hp:margin header="2834" footer="2834" gutter="0" left="4252" right="4252" top="4252" bottom="4252"/>
      </hp:pagePr>
      <hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/><hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="283" belowLine="567" aboveLine="850"/><hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="EACH_COLUMN" beneathText="0"/></hp:footNotePr>
      <hp:endNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/><hp:noteLine length="14692344" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="0" belowLine="567" aboveLine="850"/><hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/></hp:endNotePr>
      <hp:pageBorderFill type="BOTH" borderFillIDRef="1" textBorder="PAPER" headerInside="0" footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill>
      <hp:pageBorderFill type="EVEN" borderFillIDRef="1" textBorder="PAPER" headerInside="0" footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill>
      <hp:pageBorderFill type="ODD" borderFillIDRef="1" textBorder="PAPER" headerInside="0" footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill>
    </hp:secPr>
    <hp:ctrl>
      <hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="2" sameSz="1" sameGap="2267"/>
    </hp:ctrl>
    <hp:ctrl>
      <hp:footer id="" applyPage="BOTH">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="900000" paraPrIDRef="29" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
            <hp:run charPrIDRef="2">
              <hp:ctrl><hp:autoNum numType="PAGE"><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar="" supscript="0"/></hp:autoNum></hp:ctrl>
              <hp:t> / </hp:t>
              <hp:ctrl><hp:autoNum numType="TOTAL_PAGE"><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar="" supscript="0"/></hp:autoNum></hp:ctrl>
            </hp:run>
          </hp:p>
          <hp:p id="900004" paraPrIDRef="26" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
            <hp:run charPrIDRef="7"><hp:t>{self._escape(copyright_text)}</hp:t></hp:run>
          </hp:p>
        </hp:subList>
      </hp:footer>
    </hp:ctrl>{header_ctrl_xml}
  </hp:run>{"" if header_meta else f'''
  <hp:run charPrIDRef="1">
    <hp:t>{self._escape(display_title)}</hp:t>
  </hp:run>'''}
</hp:p>"""
        paras.append(first_p)
        p_id += 1

        # 타이틀 다음에 줄바꿈 한 줄(빈 문단)을 넣어 첫 문항 또는 첫 지문과의 간격 띄움
        # (머리말로 타이틀을 옮긴 경우엔 본문 첫 줄이 최대한 맨 위로 붙도록 이 간격 문단을 생략)
        if not header_meta:
            paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t> </hp:t></hp:run>
</hp:p>""")
            p_id += 1

        # 4. 문항 목록 조판
        current_chapter = ""
        last_jimum_sig = ""
        current_col_lines = 1 if header_meta else 2  # 타이틀 문단(+간격 문단) 점유
        for idx, q in enumerate(questions, start=1):
            q_major = q.get("major_chapter", "")
            q_middle = q.get("middle_chapter", "")
            q_score = q.get("score", 2)
            q_text = q.get("question_text", "")
            q_ans = str(q.get("answer", "") or "")
            q_rate = str(q.get("correct_rate", "") or "")
            q_sol = q.get("solution_text", "")
            q_source = f"{q.get('year', '')}년 {q.get('exam_type', '')} {q.get('question_num', '')}번"

            # 단원 구분 헤더 (유의미한 단원 분류가 있는 과목에서만 출력, 단원 미분류는 생략)
            has_valid_chapter = bool(q_major and q_major != "단원 미분류") or bool(q_middle and q_middle != "단원 미분류")
            chapter_str = ""
            if has_valid_chapter:
                parts = [p for p in [q_major, q_middle] if p and p != "단원 미분류"]
                chapter_str = f"[{' > '.join(parts)}]"
            if chapter_str and chapter_str != current_chapter:
                current_chapter = chapter_str
                paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="1" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="5"><hp:t>■ {self._escape(current_chapter)} ■</hp:t></hp:run>
</hp:p>""")
                p_id += 1
                current_col_lines += 2

            if mode == "solution":
                # 해설 모드
                paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="1"><hp:t>[{idx:02d}번 해설] </hp:t></hp:run>
  <hp:run charPrIDRef="6"><hp:t>정답: {self._escape(q_ans)}번 ({self._escape(q_source)})</hp:t></hp:run>
</hp:p>""")
                p_id += 1
                for s_line in (q_sol or "해설이 제공되지 않는 문항입니다.").split("\n"):
                    clean_s = s_line.strip()
                    if clean_s:
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="4"><hp:t>{self._escape(clean_s)}</hp:t></hp:run>
</hp:p>""")
                        p_id += 1
            else:
                # 문제 모드 (학생용 / 교사용)
                parsed = self._parse_question_text(
                    text=q_text,
                    score=q_score,
                    idx=idx,
                    mode=mode,
                    ans=q_ans,
                    rate=q_rate,
                    source=q_source
                )

                # 1) 지문 안내 헤더 및 본문 상자 조판 여부 결정
                current_jimum_sig = parsed.get("jimum_sig", "")
                should_render_jimum = bool((parsed.get("jimum_lines") or parsed.get("jimum_header")) and (not current_jimum_sig or current_jimum_sig != last_jimum_sig))
                if parsed.get("jimum_lines") or parsed.get("jimum_header"):
                    last_jimum_sig = current_jimum_sig

                # 문항 전체 줄 수 및 높이 추정 (2단 칼럼 레이아웃 쪼개짐 방지)
                q_lines_est = 0
                if should_render_jimum:
                    if parsed.get("jimum_header"):
                        q_lines_est += 2
                    if parsed.get("jimum_lines"):
                        for jl in parsed["jimum_lines"]:
                            q_lines_est += max(1, (len(jl) + 34) // 35) + 1

                for hl in parsed["header_lines"]:
                    q_lines_est += max(1, (len(hl) + 34) // 35)

                if parsed.get("bogi_lines"):
                    for bl in parsed["bogi_lines"]:
                        q_lines_est += max(1, (len(bl) + 34) // 35)

                if parsed.get("footer_lines"):
                    for fl in parsed["footer_lines"]:
                        q_lines_est += max(1, (len(fl) + 34) // 35)

                if parsed.get("choice_items"):
                    if parsed["is_multiline_choice"]:
                        for cl in parsed["choice_items"]:
                            q_lines_est += max(1, (len(cl) + 34) // 35)
                    else:
                        q_lines_est += 1

                # 문항/지문 조판
                # 한컴오피스 한글 레이아웃 엔진의 keepWithNext="1" 및 keepLines="1" 속성에 의해
                # 빈 공간 없이 알차게 채워지며, 문항 내부가 쪼개지지 않고 온전히 다음 단으로 자연스럽게 넘어감
                if should_render_jimum:
                    # 지문 안내 헤더: paraPrIDRef="21" (keepWithNext="1") 적용하여 바로 아래 지문 상자와 분리되지 않도록 보장
                    if parsed.get("jimum_header"):
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="1"><hp:t>{self._escape(parsed["jimum_header"])}</hp:t></hp:run>
</hp:p>""")
                        p_id += 1

                    if parsed.get("jimum_lines"):
                        for j_idx, j_line in enumerate(parsed["jimum_lines"]):
                            paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="20" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t>{self._escape(j_line)}</hp:t></hp:run>
</hp:p>""")
                            p_id += 1

                        # 지문 네모박스 아래 깔끔한 줄바꿈 한 줄(여백) 삽입
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t> </hp:t></hp:run>
</hp:p>""")
                        p_id += 1

                # 2) 헤더 발문 출력 (질문 번호 및 발문 - paraPrIDRef="21": 상단 여백 및 페이지 나뉨 방지 keepWithNext="1")
                for h_idx, h_line in enumerate(parsed["header_lines"]):
                    char_pr = "1" if h_idx == 0 else "0"
                    paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="{char_pr}"><hp:t>{self._escape(h_line)}</hp:t></hp:run>
</hp:p>""")
                    p_id += 1

                # 3) 보기 상자 조판 (< 보 기 > 상자는 질문 발문 바로 아래 배치)
                if parsed.get("bogi_lines"):
                    for b_line in parsed["bogi_lines"]:
                        # '< 보 기 >' 타이틀 행은 가운데 정렬(paraPrIDRef="23"), 내용 행은 keepWithNext="1"인 paraPrIDRef="25" 적용
                        is_bogi_title = bool(re.match(r'^[<\[]\s*보\s*기\s*[>\]]$', b_line.strip()))
                        b_para_pr = "23" if is_bogi_title else "25"
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="{b_para_pr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t>{self._escape(b_line)}</hp:t></hp:run>
</hp:p>""")
                        p_id += 1

                # 4) 후속 질문 발문 출력 (보기 상자 아래 발문 - paraPrIDRef="21")
                if parsed["footer_lines"]:
                    for f_line in parsed["footer_lines"]:
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="1"><hp:t>{self._escape(f_line)}</hp:t></hp:run>
</hp:p>""")
                        p_id += 1
                elif parsed.get("bogi_lines"):
                    # 보기 상자 바로 다음에 선택지가 올 경우, 상자 테두리와 첫 선택지가 겹치지 않도록 간격 문단 삽입
                    # keepWithNext="1"인 paraPrIDRef="24"를 적용하여 질문-보기-선택지 전체가 한 페이지/칼럼에 온전히 묶이도록 보장
                    paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="24" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t> </hp:t></hp:run>
</hp:p>""")
                    p_id += 1

                # 5) 선택지 출력 (문항 내부 결속: ①~⑤ 모든 선택지에 keepWithNext="1" 적용)
                if parsed["choice_items"]:
                    if parsed["is_multiline_choice"]:
                        for c_idx, choice in enumerate(parsed["choice_items"]):
                            # ①번부터 ⑤번 선택지까지 모두 keepWithNext="1"(paraPrIDRef="22")로 질문-보기-선택지 전체를 결속하여 문항 내부 분할 차단
                            paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="22" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t>{self._escape(choice)}</hp:t></hp:run>
</hp:p>""")
                            p_id += 1
                    else:
                        single_line = "    ".join(parsed["choice_items"])
                        paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="22" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t>{self._escape(single_line)}</hp:t></hp:run>
</hp:p>""")
                        p_id += 1

                current_col_lines += q_lines_est + 2

                # 교사용: 해설(EBSi 해설이 수집된 문항만)을 문항 바로 아래에 이어 붙인다.
                # 해설이 없는 문항은 문제·정답만 나온다.
                if mode == "teacher" and str(q_sol or "").strip():
                    paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="1"><hp:t>▶ 해설</hp:t></hp:run>
</hp:p>""")
                    p_id += 1
                    for s_line in str(q_sol).split("\n"):
                        clean_s = s_line.strip()
                        if clean_s:
                            paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="4"><hp:t>{self._escape(clean_s)}</hp:t></hp:run>
</hp:p>""")
                            p_id += 1
                    current_col_lines += 2 + str(q_sol).count("\n") + 1

            # 문항 간 명확한 여백 삽입
            paras.append(f"""<hp:p id="{p_id}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t> </hp:t></hp:run>
</hp:p>""")
            p_id += 1

        # 머리말을 쓰는 경우, secPr/머리말/꼬리말 컨트롤만 담긴 첫 번째 빈 문단이 화면상 빈 줄로 보이는 것을
        # 막기 위해 그 컨트롤들을 본문 첫 문단 안으로 옮겨 넣고, 빈 문단 자체는 제거한다.
        if header_meta and len(paras) >= 2:
            run_start = first_p.find('<hp:run charPrIDRef="1">')
            run_end = first_p.rfind('</hp:run>') + len('</hp:run>')
            ctrl_run_block = first_p[run_start:run_end]
            paras.pop(0)
            first_content_p = paras[0]
            tag_end = first_content_p.find('>', first_content_p.find('<hp:p')) + 1
            paras[0] = first_content_p[:tag_end] + '\n  ' + ctrl_run_block + first_content_p[tag_end:]

        body_content = "\n".join(paras)
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf/" xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">
{body_content}
</hs:sec>"""

    def generate_hwpx(self, output_path: str, title: str, subtitle: str, questions: List[Dict[str, Any]], mode: str = "student", header_meta: str = "") -> str:
        """
        HWPX 파일 생성 및 저장
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        section_xml = self._build_section_xml(title, subtitle, questions, mode, header_meta)

        with zipfile.ZipFile(output_path, "w") as zf:
            # 한컴 오피스 / 표준 HWPX 엔트리 순서 및 압축 규격 100% 일치
            self._create_mimetype(zf)
            self._create_version_xml(zf)
            self._create_header_xml(zf)
            zf.writestr("Contents/section0.xml", section_xml, compress_type=zipfile.ZIP_DEFLATED)
            self._create_preview_text(zf, title, subtitle)
            self._create_settings_xml(zf)
            self._create_preview_image(zf)
            self._create_container_rdf(zf)
            self._create_content_hpf(zf, title)
            self._create_container_xml(zf)
            self._create_manifest_xml(zf)

        return output_path


#你好啊，苦逼的ib学生。
#来到这里已经证明了你想要刷题的决心。
#使用代码之前请先阅读README.md文件
#这份代码其实是Gemini写的
#我自己完全不会写代码()
#下面的路径是根据windows配置的，可能会有多系统不兼容的问题
#主要是WKHTMLTOPDF_PATH这个路径需要自己改
#


import os
import re
import glob
import hashlib
import shutil
from bs4 import BeautifulSoup
import pdfkit
from multiprocessing import Pool, cpu_count

# ================= 配置区域 =================
# 获取脚本所在目录（比 os.getcwd() 更稳：避免从别的目录运行时找不到输入/输出）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 定义教学大纲章节目录
SYLLABUS_DIR = os.path.join(BASE_DIR, "syllabus_sections")
# 定义题目节点树目录
QUESTIONS_DIR = os.path.join(BASE_DIR, "question_node_trees")
# 定义输出PDF的目录
OUTPUT_DIR = os.path.join(BASE_DIR, "output_pdfs")

# 自动寻找 wkhtmltopdf 路径，兼容 Windows/Mac/Linux
# 如果找不到，尝试使用默认的 Windows 路径
WKHTMLTOPDF_PATH = shutil.which("wkhtmltopdf")
if not WKHTMLTOPDF_PATH and os.name == 'nt':
    WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'

# PDF 生成选项配置
PDF_OPTIONS = {
    'page-size': 'Letter',          # 纸张大小
    'margin-top': '0.5in',          # 上边距
    'margin-right': '0.5in',        # 右边距
    'margin-bottom': '0.5in',       # 下边距
    'margin-left': '0.5in',         # 左边距
    'encoding': "UTF-8",            # 编码格式
    'enable-local-file-access': None, # 允许访问本地文件（用于加载图片等）
    'quiet': None                   # 静默模式，不输出日志
}
# ===========================================

def get_pdfkit_config():
    """
    获取 pdfkit 的配置对象。
    如果指定路径存在 wkhtmltopdf，则返回配置对象，否则返回 None。
    """
    if WKHTMLTOPDF_PATH and os.path.exists(WKHTMLTOPDF_PATH):
        return pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
    return None

def clean_title(text):
    """
    清洗标题文本。
    去除多余空格，并提取 Structure 或 Reactivity 及其后的章节编号（如 1.1）。
    """
    text = " ".join(text.split())
    # 正则匹配 Structure 或 Reactivity 开头的章节号，例如 "Structure 1.1"
    match = re.search(r'(Structure|Reactivity)\s+(\d+\.\d+)(?!\.\d+)', text, re.I)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None

def parse_single_question(q_filename):
    """
    解析单个题目文件。
    读取HTML文件，提取题目ID、试卷类型、题目内容、分值（如有）和评分标准。
    """
    file_path = os.path.join(QUESTIONS_DIR, q_filename)
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # 提取题目代码 (ID)
        q_id_tag = soup.select_one('.qn_code')
        q_id = q_id_tag.get_text(strip=True) if q_id_tag else "Unknown ID"
        
        # 识别 Paper 类型 (Paper 1A, Paper 1B, Paper 2)
        paper_type = "Paper 2" # 默认为 Paper 2
        properties = soup.select('.property_value')
        for prop in properties:
            text = prop.get_text(strip=True)
            if "Paper 1A" in text: paper_type = "Paper 1A"; break
            if "Paper 1B" in text: paper_type = "Paper 1B"; break
            if "Paper 2" in text: paper_type = "Paper 2"; break
        
        # 根据题目ID修正 Paper 类型（如果ID包含1A或1B但被识别为Paper 2）
        if paper_type == "Paper 2" and "1A" in q_id: paper_type = "Paper 1A"
        if paper_type == "Paper 2" and "1B" in q_id: paper_type = "Paper 1B"

        # 提取分值 (Marks)
        # 逻辑：在 HTML 文本中寻找类似 [2]、[2 marks] 之类的标记
        # 说明：Paper 1A 通常为客观题/填空，默认不显示 marks（可按需要改）
        q_marks = ""
        if paper_type != "Paper 1A":
            full_text = soup.get_text(" ", strip=True)
            mark_match = re.search(r'\[(\d+)\s*marks?\]', full_text, re.I)
            if not mark_match:
                mark_match = re.search(r'\[(\d+)\]', full_text)
            if mark_match:
                q_marks = f"[{mark_match.group(1)} marks]"
        
        # 提取题目主体内容
        q_body = soup.select_one('.qc_body')
        if not q_body:
            return None

        # 提取评分标准 (Markscheme)
        ms_tag = soup.select_one('.qc_markscheme .card-body')

        # 处理图片路径，将其转换为绝对路径以便 pdfkit 正确加载
        # 题干 + 评分标准里都有可能出现图片
        for container in [q_body, ms_tag]:
            if not container:
                continue
            for img in container.find_all('img'):
                if img.get('src') and not img['src'].startswith(('http', 'data:')):
                    abs_img_path = os.path.abspath(os.path.join(QUESTIONS_DIR, img['src']))
                    img['src'] = 'file:///' + abs_img_path.replace('\\', '/')

        q_ms = str(ms_tag) if ms_tag else "No Markscheme"

        return {"id": q_id, "body": str(q_body), "ms": q_ms, "paper": paper_type, "marks": q_marks}
    except: return None

def get_questions_from_html(soup):
    """
    从 HTML soup 对象中提取所有题目文件的链接。
    """
    q_files = set()
    for a in soup.find_all('a', href=True):
        if "question_node_trees" in a['href']:
            q_files.add(os.path.basename(a['href']))
    return q_files

def process_section(target_info):
    """
    处理单个章节：读取题目，分类，生成HTML，并转换为PDF。
    """
    fname, title = target_info
    file_path = os.path.join(SYLLABUS_DIR, fname)
    
    # 从标题中提取前缀和编号，用于生成输出文件名
    match = re.search(r'(S|R)[a-z]+\s+(\d+)\.(\d+)', title, re.I)
    if match:
        prefix = match.group(1).lower()
        base_out = f"{prefix}{match.group(2)}_{match.group(3)}"
    else:
        safe = re.sub(r'[^a-zA-Z0-9._-]+', '_', title).strip('_')
        base_out = safe or "section"

    out_main_name = f"{base_out}.pdf"
    out_sheet_name = f"{base_out}_answers.pdf"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    # 获取该章节下的所有题目文件
    all_q_files = get_questions_from_html(soup)
    
    # 检查是否有子章节链接，如果有，也提取其中的题目
    for a in soup.find_all('a', href=True):
        if "syllabus_sections" in a['href']:
            sub_fname = os.path.basename(a['href'])
            if sub_fname != fname:
                sub_path = os.path.join(SYLLABUS_DIR, sub_fname)
                if os.path.exists(sub_path):
                    with open(sub_path, 'r', encoding='utf-8') as sf:
                        all_q_files.update(get_questions_from_html(BeautifulSoup(sf.read(), 'html.parser')))

    def _normalize_question_text(html_fragment: str) -> str:
        """用于去重的题干文本规范化：
        - 去掉 HTML 标签
        - 统一 nbsp/全角空白
        - 把多余的换行/空格折叠为单个空格
        """
        text = re.sub(r'<[^>]+>', ' ', html_fragment)
        text = text.replace('\u00a0', ' ').replace('\u3000', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _pick_better_question(existing: dict, candidate: dict) -> dict:
        """同一题号/同一题干出现多份时，尽量选择信息更完整的一份。"""
        if not existing:
            return candidate

        # 优先保留有评分标准的版本
        existing_has_ms = existing.get('ms') and existing.get('ms') != 'No Markscheme'
        candidate_has_ms = candidate.get('ms') and candidate.get('ms') != 'No Markscheme'
        if candidate_has_ms and not existing_has_ms:
            return candidate
        if existing_has_ms and not candidate_has_ms:
            return existing

        # 优先保留能提取到 marks 的版本
        existing_has_marks = bool(existing.get('marks'))
        candidate_has_marks = bool(candidate.get('marks'))
        if candidate_has_marks and not existing_has_marks:
            return candidate
        if existing_has_marks and not candidate_has_marks:
            return existing

        # 题干更长通常信息更完整（少被截断/少缺图）
        existing_len = len(_normalize_question_text(existing.get('body', '')))
        candidate_len = len(_normalize_question_text(candidate.get('body', '')))
        if candidate_len > existing_len:
            return candidate

        return existing

    # --- 核心改进：对比题号 + 空白规范化后内容指纹去重 ---
    # 第一层：按题号(q_id)去重，避免同一题被重复抓取
    by_qid = {}
    # 第二层：按“规范化题干”的指纹去重，处理题干只差空格/回车的重复
    by_fingerprint = {}

    for q_file in sorted(list(all_q_files)):
        data = parse_single_question(q_file)
        if not data:
            continue

        qid = (data.get('id') or '').strip()
        normalized = _normalize_question_text(data.get('body', ''))
        content_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()

        # 1) 优先按题号去重（题号正常时更可靠）
        if qid and qid != 'Unknown ID':
            if qid in by_qid:
                by_qid[qid] = _pick_better_question(by_qid[qid], data)
            else:
                by_qid[qid] = data
            continue

        # 2) 题号缺失/异常时，退化到内容指纹去重
        if content_hash in by_fingerprint:
            by_fingerprint[content_hash] = _pick_better_question(by_fingerprint[content_hash], data)
        else:
            by_fingerprint[content_hash] = data

    # 把两种来源合并，再做一次“内容指纹”层面的最终去重
    unique_questions = {}
    for data in list(by_qid.values()) + list(by_fingerprint.values()):
        normalized = _normalize_question_text(data.get('body', ''))
        content_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()
        if content_hash in unique_questions:
            unique_questions[content_hash] = _pick_better_question(unique_questions[content_hash], data)
        else:
            unique_questions[content_hash] = data

    # 初始化分类字典
    categories = {"Paper 1A": [], "Paper 1B": [], "Paper 2": []}
    
    # 按照 Paper 类型重新分类去重后的题目
    for data in unique_questions.values():
        cat_key = data['paper'] if data['paper'] in categories else "Paper 2"
        categories[cat_key].append(data)

    # --- 渲染逻辑：生成两个 PDF ---
    # 1) 主 PDF：题目 + Detailed Markscheme（单独分页）
    main_questions_html = f"<h1>{title}</h1>"
    main_answers_html = "<div style='page-break-before: always; text-align: center; border-bottom: 2px solid #000;'><h1>Detailed Markscheme</h1></div>"

    # 2) Answer Sheet：用于快速核对
    sheet_html = f"<h1 style='color:#2c3e50;'>Answer Sheet: {title}</h1>"

    global_count = 1
    has_content = False

    for cat in ["Paper 1A", "Paper 1B", "Paper 2"]:
        if not categories[cat]:
            continue

        has_content = True
        main_questions_html += f"<div class='paper-header'>{cat}</div>"
        main_answers_html += f"<div style='background:#f4f4f4; padding:5px; margin: 15px 0;'><b>{cat}</b></div>"
        sheet_html += f"<div style='background:#2c3e50; color:white; padding:5px; margin-top:20px;'><b>{cat} Quick Check</b></div>"

        # Paper 1A：Answer Sheet 特殊排版（5 个一组，显示答案字母）
        if cat == "Paper 1A":
            sheet_html += "<div style='display:flex; flex-wrap:wrap;'>"
            for i, q in enumerate(categories[cat]):
                group_style = "margin-right: 30px;" if (i + 1) % 5 == 0 else "margin-right: 10px;"

                # 提取选择题答案字母：从评分标准文本中抓 A/B/C/D
                letter = "?"
                if q.get('ms') and q['ms'] != 'No Markscheme':
                    ans_soup = BeautifulSoup(q['ms'], 'html.parser')
                    raw_ans = ans_soup.get_text(" ", strip=True)
                    letter_match = re.search(r'\b([A-D])\b', raw_ans)
                    if letter_match:
                        letter = letter_match.group(1)

                sheet_html += (
                    f"<div style='width:80px; padding:10px; border-bottom:1px solid #eee; {group_style}'>"
                    f"<b>{global_count}.</b> <span style='color:#c0392b; font-size:1.2em;'>{letter}</span>"
                    f"</div>"
                )

                main_questions_html += f"""
                <div class="question-wrapper">
                    <div class="q-meta">Question {global_count}<span style="float:right; font-weight: normal; font-size: 9pt; color: #777;">Ref: {q['id']}</span></div>
                    <div class="q-content">{q['body']}</div>
                    <div class="answer-lines"><div class='line'></div></div>
                </div>"""

                main_answers_html += f"""
                <div class="ans-block">
                    <div class="ans-num">Question {global_count} ({q['id']})</div>
                    <div class="ans-ms">{q['ms']}</div>
                </div>"""

                global_count += 1
            sheet_html += "</div>"
            continue

        # Paper 1B / Paper 2
        for q in categories[cat]:
            sheet_html += (
                f"<div style='margin:10px 0; border-bottom:1px dashed #ccc; padding-bottom:5px;'>"
                f"<b>{global_count}.</b> {q.get('marks','')} <span style='color:#777; font-size:0.8em;'>({q['id']})</span>"
                f"<div style='margin-top:5px; color:#444;'>{q['ms']}</div>"
                f"</div>"
            )

            main_questions_html += f"""
            <div class="question-wrapper">
                <div class="q-meta">
                    Question {global_count}
                    <span class="q-marks">{q.get('marks','')}</span>
                    <span style="float:right; font-weight: normal; font-size: 9pt; color: #777;">Ref: {q['id']}</span>
                </div>
                <div class="q-content">{q['body']}</div>
                <div class="answer-lines">{"<div class='line'></div>" * 4}</div>
            </div>"""

            main_answers_html += f"""
            <div class="ans-block">
                <div class="ans-num">Question {global_count} ({q['id']}) <span style=\"color:#777; font-size:0.9em;\">{q.get('marks','')}</span></div>
                <div class="ans-ms">{q['ms']}</div>
            </div>"""

            global_count += 1

    if not has_content:
        return f"SKIP: {base_out}"

    style = """
    <style>
        body { font-family: "Noto Sans", "Noto Sans SC", sans-serif; line-height: 1.5; color: #333; }
        h1 { text-align: center; margin-bottom: 30px; }
        .paper-header { background: #000; color: #fff; padding: 8px 15px; font-weight: bold; margin: 30px 0 15px 0; }
        .question-wrapper { page-break-inside: avoid; margin-bottom: 40px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .q-meta { font-weight: bold; font-size: 13pt; border-bottom: 2px solid #333; margin-bottom: 10px; }
        .q-marks { color: #2c3e50; margin-left: 15px; font-size: 11pt; }
        .q-content { margin-bottom: 15px; }
        .line { border-bottom: 1px solid #999; height: 32px; margin-bottom: 2px; }

        .ans-block { page-break-inside: avoid; border-bottom: 1px solid #ddd; margin-bottom: 20px; padding-bottom: 10px; }
        .ans-num { font-weight: bold; color: #c0392b; margin-bottom: 5px; }
        .ans-ms { font-size: 10pt; background: #fafafa; padding: 8px; border-radius: 3px; }

        img { max-width: 100%; height: auto; }
        table, td, th { border: 1px solid #444; border-collapse: collapse; padding: 5px; font-family: sans-serif !important; }
    </style>
    """

    try:
        config = get_pdfkit_config()

        full_html = (
            f"<html><head><meta charset='utf-8'>{style}</head>"
            f"<body>{main_questions_html}{main_answers_html}</body></html>"
        )
        pdfkit.from_string(
            full_html,
            os.path.join(OUTPUT_DIR, out_main_name),
            options=PDF_OPTIONS,
            configuration=config,
        )

        sheet_full_html = (
            f"<html><head><meta charset='utf-8'>{style}</head>"
            f"<body>{sheet_html}</body></html>"
        )
        pdfkit.from_string(
            sheet_full_html,
            os.path.join(OUTPUT_DIR, out_sheet_name),
            options=PDF_OPTIONS,
            configuration=config,
        )

        main_out_path = os.path.join(OUTPUT_DIR, out_main_name)
        sheet_out_path = os.path.join(OUTPUT_DIR, out_sheet_name)
        if not os.path.exists(main_out_path) or not os.path.exists(sheet_out_path):
            return (
                f"FAILED: {base_out} | PDF not written. "
                f"Check wkhtmltopdf install/path (WKHTMLTOPDF_PATH={WKHTMLTOPDF_PATH}) and output dir ({OUTPUT_DIR})."
            )

        return f"SUCCESS: {base_out} (Main + Answer Sheet, Unique Questions: {global_count-1})"
    except Exception as e:
        return f"FAILED: {base_out} | {str(e)}"

def main():
    """
    主函数：扫描目录，查找章节文件，并使用多进程处理。
    """
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    targets = []
    print("Scanning syllabus files...")
    # 遍历 syllabus_sections 目录下的所有 HTML 文件
    for f in glob.glob(os.path.join(SYLLABUS_DIR, "*.html")):
        try:
            with open(f, 'r', encoding='utf-8') as fo:
                soup = BeautifulSoup(fo.read(), 'html.parser')
                h1 = soup.find('h1')
                if h1:
                    cleaned = clean_title(h1.get_text())
                    if cleaned: targets.append((os.path.basename(f), cleaned))
        except: continue
    
    print(f"Found {len(targets)} sections. Utilizing 13700K power...")
    # 使用多进程池并行处理章节
    with Pool(processes=max(1, cpu_count() - 2)) as p:
        results = p.map(process_section, targets)
    for r in results: print(r)

if __name__ == "__main__":
    main()

    #Hey Virgil, 你动不动就刷题卡住的日子结束了
    #把题库给我
    #If you want it, then you have to take it.
    #"意义不明的鼓点"
    #"大病的曲调"
    #I AM THE STORM THAT IS APPROOOOOOOOOACHING!!!

    #哦对还有，这份代码是我生日这天写完的
    #祝你刷题顺利

    #Muchen Jiang

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
import time
from bs4 import BeautifulSoup
import pdfkit
from multiprocessing import Pool, cpu_count

# ================= 配置区域 =================
BASE_DIR = os.getcwd()
SYLLABUS_DIR = os.path.join(BASE_DIR, "syllabus_sections")
QUESTIONS_DIR = os.path.join(BASE_DIR, "question_node_trees")
OUTPUT_DIR = os.path.join(BASE_DIR, "output_pdfs")

# 请确保此处路径正确
WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'

PDF_OPTIONS = {
    'page-size': 'Letter',
    'margin-top': '0.5in',
    'margin-right': '0.5in',
    'margin-bottom': '0.5in',
    'margin-left': '0.5in',
    'encoding': "UTF-8",
    'enable-local-file-access': None,
    'quiet': None 
}
# ===========================================

def get_pdfkit_config():
    if os.path.exists(WKHTMLTOPDF_PATH):
        return pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
    return None

def clean_title(text):
    text = " ".join(text.split())
    match = re.search(r'(Structure|Reactivity)\s+(\d+\.\d+)(?!\.\d+)', text, re.I)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None

def parse_single_question(q_filename):
    file_path = os.path.join(QUESTIONS_DIR, q_filename)
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        q_id_tag = soup.select_one('.qn_code')
        q_id = q_id_tag.get_text(strip=True) if q_id_tag else "Unknown ID"
        
        # 识别 Paper 类型
        paper_type = "Paper 2" 
        properties = soup.select('.property_value')
        for prop in properties:
            text = prop.get_text(strip=True)
            if "Paper 1A" in text: paper_type = "Paper 1A"; break
            if "Paper 1B" in text: paper_type = "Paper 1B"; break
            if "Paper 2" in text: paper_type = "Paper 2"; break
        
        if paper_type == "Paper 2" and "1A" in q_id: paper_type = "Paper 1A"
        if paper_type == "Paper 2" and "1B" in q_id: paper_type = "Paper 1B"
        
        q_body = soup.select_one('.qc_body')
        if not q_body: return None
        ms_tag = soup.select_one('.qc_markscheme .card-body')
        q_ms = str(ms_tag) if ms_tag else "No Markscheme"

        for img in q_body.find_all('img'):
            if img.get('src') and not img['src'].startswith(('http', 'data:')):
                abs_img_path = os.path.abspath(os.path.join(QUESTIONS_DIR, img['src']))
                img['src'] = 'file:///' + abs_img_path.replace('\\', '/')

        return {"id": q_id, "body": str(q_body), "ms": q_ms, "paper": paper_type}
    except: return None

def get_questions_from_html(soup):
    q_files = set()
    for a in soup.find_all('a', href=True):
        if "question_node_trees" in a['href']:
            q_files.add(os.path.basename(a['href']))
    return q_files

def process_section(target_info):
    fname, title = target_info
    file_path = os.path.join(SYLLABUS_DIR, fname)
    
    match = re.search(r'(S|R)[a-z]+\s+(\d+)\.(\d+)', title, re.I)
    prefix = match.group(1).lower()
    out_name = f"{prefix}{match.group(2)}_{match.group(3)}.pdf"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    all_q_files = get_questions_from_html(soup)
    for a in soup.find_all('a', href=True):
        if "syllabus_sections" in a['href']:
            sub_fname = os.path.basename(a['href'])
            if sub_fname != fname:
                sub_path = os.path.join(SYLLABUS_DIR, sub_fname)
                if os.path.exists(sub_path):
                    with open(sub_path, 'r', encoding='utf-8') as sf:
                        all_q_files.update(get_questions_from_html(BeautifulSoup(sf.read(), 'html.parser')))

    categories = {"Paper 1A": [], "Paper 1B": [], "Paper 2": []}
    for q_file in sorted(list(all_q_files)):
        data = parse_single_question(q_file)
        if data:
            cat_key = data['paper'] if data['paper'] in categories else "Paper 2"
            categories[cat_key].append(data)

    questions_html = ""
    answers_html = "<div style='page-break-before: always; text-align: center; border-bottom: 2px solid #000;'><h1>Answer Key</h1></div>"
    
    global_count = 1
    has_content = False

    for cat in ["Paper 1A", "Paper 1B", "Paper 2"]:
        if categories[cat]:
            has_content = True
            # 添加 Paper 标题栏
            questions_html += f"<div class='paper-header'>{cat}</div>"
            answers_html += f"<div style='background:#f4f4f4; padding:5px; margin: 15px 0;'><b>{cat} Answers</b></div>"
            
            for q in categories[cat]:
                # 题目：顶端一行显示 Question 序号 和 Reference Code
                questions_html += f"""
                <div class="question-wrapper">
                    <div class="q-meta">Question {global_count} <span style="float:right;">Ref: {q['id']}</span></div>
                    <div class="q-content">{q['body']}</div>
                    <div class="answer-lines">{"<div class='line'></div>" * (1 if cat == 'Paper 1A' else 4)}</div>
                </div>"""
                
                # 答案：对应序号
                answers_html += f"""
                <div class="ans-block">
                    <div class="ans-num">Question {global_count} ({q['id']})</div>
                    <div class="ans-ms">{q['ms']}</div>
                </div>"""
                
                global_count += 1

    if not has_content: return f"SKIP: {out_name}"

    full_html = f"""
    <html>
    <head>
        <meta charset='utf-8'>
        <style>
            body {{ font-family: "Noto Sans", "Noto Sans SC", sans-serif; line-height: 1.5; color: #333; }}
            h1 {{ text-align: center; margin-bottom: 30px; }}
            .paper-header {{ background: #000; color: #fff; padding: 8px 15px; font-weight: bold; margin: 30px 0 15px 0; }}
            .question-wrapper {{ page-break-inside: avoid; margin-bottom: 40px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            .q-meta {{ font-weight: bold; font-size: 13pt; border-bottom: 2px solid #333; margin-bottom: 10px; }}
            .q-content {{ margin-bottom: 15px; }}
            .line {{ border-bottom: 1px solid #999; height: 32px; margin-bottom: 2px; }}
            
            .ans-block {{ page-break-inside: avoid; border-bottom: 1px solid #ddd; margin-bottom: 20px; padding-bottom: 10px; }}
            .ans-num {{ font-weight: bold; color: #c0392b; margin-bottom: 5px; }}
            .ans-ms {{ font-size: 10pt; background: #fafafa; padding: 8px; border-radius: 3px; }}
            
            img {{ max-width: 100%; height: auto; }}
            table, td, th {{ border: 1px solid #444; border-collapse: collapse; padding: 5px; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        {questions_html}
        {answers_html}
    </body>
    </html>
    """
    
    try:
        pdfkit.from_string(full_html, os.path.join(OUTPUT_DIR, out_name), options=PDF_OPTIONS, configuration=get_pdfkit_config())
        return f"SUCCESS: {out_name} ({global_count-1} Questions)"
    except Exception as e:
        return f"FAILED: {out_name} | {str(e)}"

def main():
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    targets = []
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

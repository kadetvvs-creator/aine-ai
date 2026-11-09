#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AINE · ИИ-аналитик документов — многостадийный конвейер (как Dify/n8n).

Стадии:
  1. Парсер/расчёт (детерминированный pandas — суммы, средние, топ, разницы)
  2. Аналитик (LLM: сухие цифры → 3–5 экономических выводов)
  3. Копирайтер (LLM: выводы → финальный текст в корпоративном стиле)
  4. Генератор (графики matplotlib + Word/PDF/PPT/Excel)
"""
import sys, os, re, subprocess, json
sys.path.insert(0, "/home/aine/workspace")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-cache")
os.makedirs("/tmp/mpl-cache", exist_ok=True)

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from aine_helper import ask

OUT = "/home/aine/workspace/ai_out"
ANALYST = os.environ.get("AI_DOCS_ANALYST", "Qwen2.5-7B-Instruct-Q4_K_M")
WRITER = os.environ.get("AI_DOCS_WRITER", "Llama-3.1-8B-Instruct-Q4_K_M")


def ask_direct(prompt, model, max_tokens=800):
    """Прямой вызов модели (без агент-прокси и инструментов) — чистый текст."""
    import requests as _rq
    base = "http://127.0.0.1:8095" if "7B" in model and "Coder" not in model else "http://127.0.0.1:8080"
    r = _rq.post(base + "/v1/chat/completions",
                 headers={"Authorization": "Bearer 5yicZ3KPrbRePFaxJvl7MV5D6FNofoBD",
                          "Content-Type": "application/json"},
                 json={"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.4}, timeout=600)
    return r.json()["choices"][0]["message"]["content"]


def _describe_image(img_bytes):
    """Описать картинку через vision-модель (VL-7B)."""
    import base64, requests as _rq
    try:
        b64 = base64.b64encode(img_bytes).decode()
        r = _rq.post("http://127.0.0.1:8082/v1/chat/completions",
                     headers={"Authorization": "Bearer 5yicZ3KPrbRePFaxJvl7MV5D6FNofoBD"},
                     json={"model": "vision",
                           "messages": [{"role": "user", "content": [
                               {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                               {"type": "text", "text": "Кратко опиши, что на изображении (1-2 предложения)"}]}],
                           "max_tokens": 80}, timeout=180)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(изображение не распознано: {type(e).__name__})"


def _read_excel_deep(path):
    """Глубокое чтение Excel: листы, формулы, комментарии, имена, диаграммы, картинки, VBA."""
    import openpyxl
    parts = []
    wb = openpyxl.load_workbook(path, data_only=False)
    if wb.defined_names:
        parts.append("Именованные диапазоны: " + ", ".join(str(n) for n in list(wb.defined_names.keys())[:20]))
    for ws in wb.worksheets:
        parts.append(f"\nЛист «{ws.title}»:")
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 100), values_only=False):
            cells = [f"{c.coordinate}={c.value}" for c in row if c.value is not None]
            if cells:
                parts.append("  " + " | ".join(cells[:20]))
        comments = getattr(ws, "_comments", None)
        if comments:
            parts.append(f"  Комментарии ({len(comments)}):")
            for coord, c in list(comments.items())[:10]:
                parts.append(f"    {coord}: {c.text}")
        charts = getattr(ws, "_charts", None)
        if charts:
            for ch in charts[:5]:
                ttl = getattr(ch, "title", None)
                ns = len(getattr(ch, "series", []) or [])
                parts.append(f"  Диаграмма: {type(ch).__name__}, серий: {ns}" + (f" «{ttl}»" if ttl else ""))
        imgs = getattr(ws, "_images", None)
        if imgs:
            parts.append(f"  Изображений: {len(imgs)}")
            for img in imgs[:3]:
                try:
                    parts.append("    - " + _describe_image(img._data()))
                except Exception as e:
                    parts.append(f"    - (не удалось: {type(e).__name__})")
    if path.lower().endswith((".xlsm", ".xlsb")):
        try:
            import oletools.olevba as olevba
            vba = olevba.VBA_Parser(path)
            if vba.detect_vba_macros():
                for (fn, sp, vfn, code) in vba.extract_macros():
                    parts.append(f"\nVBA-макрос «{vfn}»:\n{code[:1500]}")
            vba.close()
        except Exception as e:
            parts.append(f"\nVBA: {type(e).__name__}: {e}")
    content = "\n".join(parts)
    tables = pd.read_excel(path, sheet_name=None)
    return content, tables


def read_any(path):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xlsm", "xlsb", "xls"):
        return _read_excel_deep(path)
    if ext == "csv":
        df = pd.read_csv(path)
        return df.head(60).to_string(), {"данные": df}
    if ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs), {}
    if ext == "pdf":
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages), {}
        except Exception as e:
            return f"(PDF не прочитан: {e})", {}
    if ext in ("txt", "md"):
        return open(path, encoding="utf-8", errors="replace").read(), {}
    return f"(формат .{ext} не поддерживается)", {}


def stage_calculate(tables):
    """Стадия 1: детерминированный расчёт (не ИИ). Пропускает Unnamed/пустые колонки."""
    parts = []
    for name, df in tables.items():
        # убрать колонки-артефакты (Unnamed) и полностью пустые
        cols = [c for c in df.columns if "Unnamed" not in str(c)]
        df = df[cols].dropna(how="all", axis=1)
        num = df.select_dtypes("number")
        if num.empty:
            continue
        parts.append(f"Лист «{name}»:")
        parts.append("  Итого: " + "; ".join(f"{c}={df[c].sum():.0f}" for c in num.columns if df[c].notna().any()))
        parts.append("  Среднее: " + "; ".join(f"{c}={df[c].mean():.1f}" for c in num.columns if df[c].notna().any()))
        c0 = num.columns[0]
        cat = next((c for c in df.columns if df[c].dtype == object and df[c].notna().any()), None)
        top = df.nlargest(3, c0).to_dict("records")
        parts.append("  Топ-3: " + "; ".join(
            f"{r.get(cat, '') or ''}:{r.get(c0)}" for r in top))
    return "\n".join(parts) if parts else "нет числовых данных"


def _clean(md):
    i = md.find("# ")
    if i > 0:
        md = md[i:]
    # убрать «- »/«* » перед заголовками (частый артефакт модели)
    md = re.sub(r'(?m)^[-*•]\s+(?=#{1,3}\s)', '', md)
    return md.strip()


def _charts(tables, out_dir):
    charts = []
    try:
        for name, df in tables.items():
            num = df.select_dtypes("number")
            if num.empty:
                continue
            cat = next((c for c in df.columns if df[c].dtype == object and df[c].nunique() <= 30), None)
            for col in num.columns[:3]:
                try:
                    fig, ax = plt.subplots(figsize=(7, 3.5))
                    (df.groupby(cat)[col].sum().plot(kind="bar", ax=ax) if cat
                     else df[col].plot(kind="line", marker="o", ax=ax))
                    ax.set_title(f"{col} — «{name}»")
                    plt.tight_layout()
                    fn = os.path.join(out_dir, f"график_{re.sub(r'[^a-zа-я0-9]+', '_', str(name))[:20]}_{re.sub(r'[^a-zа-я0-9]+', '_', str(col))[:20]}.png")
                    plt.savefig(fn, dpi=110); plt.close(); charts.append(fn)
                except Exception:
                    plt.close()
    except Exception:
        pass
    return charts


def _word(md, path):
    from docx import Document
    doc = Document()
    for line in md.split("\n"):
        s = line.rstrip()
        if s.startswith("# "):
            doc.add_heading(s[2:].strip(), 0)
        elif s.startswith("## "):
            doc.add_heading(s[3:].strip(), 1)
        elif s.startswith("### "):
            doc.add_heading(s[4:].strip(), 2)
        elif s.strip().startswith(("- ", "* ", "• ", "– ")):
            doc.add_paragraph(s.strip().lstrip("-*•– ").strip(), style="List Bullet")
        elif s.strip():
            doc.add_paragraph(s.strip())
    doc.save(path)


def _pdf(docx_path, out_dir):
    try:
        pdir = "/tmp/lo_profile_%d" % os.getpid()
        os.makedirs(pdir, exist_ok=True)
        subprocess.run(["soffice", "--headless", "-env:UserInstallation=file://" + pdir,
                        "--convert-to", "pdf", "--outdir", out_dir, docx_path],
                       timeout=240, capture_output=True)
        p = docx_path[:-5] + ".pdf"
        return p if os.path.exists(p) else None
    except Exception:
        return None


def _pptx(md, path):
    try:
        from pptx import Presentation
        prs = Presentation()
        lines = md.split("\n")
        title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "Отчёт")
        s = prs.slides.add_slide(prs.slide_layouts[0])
        s.shapes.title.text = title[:90]
        s.placeholders[1].text = "AINE · аналитический конвейер"
        blocks, cur = [], None
        for l in lines:
            if l.startswith("## "):
                cur = [l[3:].strip(), []]
                blocks.append(cur)
            elif cur is not None and l.strip():
                cur[1].append(l.strip())
        for h, body in blocks:
            if not body:
                continue
            sl = prs.slides.add_slide(prs.slide_layouts[1])
            sl.shapes.title.text = h[:80]
            sl.placeholders[1].text = "\n".join(body)[:1400]
        prs.save(path)
        return True
    except Exception as e:
        print("PPTX:", e)
        return False


def process(path, command, out_dir=OUT, formats=None, do_charts=True):
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r"[^a-zа-я0-9\-]+", "_", os.path.splitext(os.path.basename(path))[0])
    content, tables = read_any(path)
    formats = formats or ["docx", "pdf", "pptx", "xlsx"]

    # Стадия 1 — расчёт (числовой) + сохранить исходную таблицу для ИИ
    calc = stage_calculate(tables)
    material = content[:7000]
    if calc and calc != "нет числовых данных":
        material += "\n\nЧисловой расчёт:\n" + calc

    # Стадия 2 — аналитик (ИИ видит исходную таблицу + расчёт)
    insights = ask_direct(
        "Ты финансовый директор. Исходные данные (таблица целиком):\n" + material +
        "\n\nВыдели 3–5 ключевых выводов и экономических плюсов, "
        "обязательно с конкретными цифрами. Кратко, по-русски.",
        model=ANALYST, max_tokens=800)

    # Стадия 3 — копирайтер (выводы → финальный текст)
    md = _clean(ask_direct(
        "Ты копирайтер. Задача руководителя:\n" + command +
        "\n\nВыводы аналитика:\n" + insights +
        "\n\nНапиши финальный документ в корпоративном стиле, markdown: "
        "«# Заголовок», «## Раздел», «- пункт». По-русски, по делу.",
        model=WRITER, max_tokens=1800))

    # Стадия 4 — документы (по выбранным форматам) + графики
    files = {}
    if "docx" in formats or "pdf" in formats:
        docx = os.path.join(out_dir, base + "_документ.docx")
        _word(md, docx)
        if "docx" in formats:
            files["docx"] = docx
        if "pdf" in formats:
            pdf = _pdf(docx, out_dir)
            if pdf:
                files["pdf"] = pdf
    if "pptx" in formats:
        pptx = os.path.join(out_dir, base + "_презентация.pptx")
        if _pptx(md, pptx):
            files["pptx"] = pptx
    if tables and "xlsx" in formats:
        xlsx = os.path.join(out_dir, base + "_данные.xlsx")
        with pd.ExcelWriter(xlsx) as w:
            for n, df in tables.items():
                df.to_excel(w, sheet_name=str(n)[:30])
        files["xlsx"] = xlsx
        if do_charts:
            files["charts"] = _charts(tables, out_dir)
    calc_display = content[:2500] + ("\n\nЧисловой расчёт:\n" + calc if calc != "нет числовых данных" else "")
    return {"calc": calc_display, "insights": insights, "final": md, "files": files}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ai_docs.py <файл> [команда] [--json] [--formats=docx,pdf] [--no-charts]"); sys.exit(1)
    inp = sys.argv[1]
    cmd = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "проанализируй и сделай отчёт"
    formats = None
    do_charts = True
    out_dir = OUT
    for a in sys.argv:
        if a.startswith("--formats="):
            formats = a.split("=", 1)[1].split(",")
        if a == "--no-charts":
            do_charts = False
        if a.startswith("--out-dir="):
            out_dir = a.split("=", 1)[1]
    r = process(inp, cmd, formats=formats, do_charts=do_charts, out_dir=out_dir)
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print("--- ① Расчёт (pandas) ---"); print(r["calc"][:400])
        print("\n--- ② Выводы аналитика ---"); print(r["insights"][:500])
        print("\n--- ③ Финальный текст ---"); print(r["final"][:800])
        print("\n--- ④ Файлы ---")
        for k, v in r["files"].items():
            print(f"  {k}: {v if not isinstance(v, list) else f'{len(v)} шт'}")

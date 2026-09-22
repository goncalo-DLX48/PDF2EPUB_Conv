#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf2epub — conversor genérico de PDF (texto) para EPUB 3.

Uso:
    python pdf2epub.py livro.pdf
    python pdf2epub.py livro.pdf -o saida.epub
    python pdf2epub.py livro.pdf --titulo "O Meu Livro" --autor "Fulano"
    python pdf2epub.py livro.pdf --lingua en
    python pdf2epub.py livro.pdf --nao-dividir

Dependência:
    pymupdf   (pip install pymupdf)
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
import uuid
import zipfile
from collections import Counter
from statistics import median

class PDFError(Exception):
    """Erro de domínio do conversor (ex.: PDF sem texto, sem páginas).

    Usado em vez de sys.exit() para que a GUI possa capturar o erro
    sem fechar. A CLI captura esta exceção em main() e sai com o
    código apropriado, mantendo o comportamento anterior.
    """


try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

# ===========================================================================
#  Texto / HTML
# ===========================================================================

def esc(t):
    return html.escape(t, quote=True)


def clean(t):
    return re.sub(r"\s+", " ", t).strip()


def to_roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def glue_needed(prev_piece, start):
    if not prev_piece:
        return False
    if prev_piece.endswith(">"):
        return start not in ".,:;!?)]" + "\u201d\u2019"
    if start in ".,:;!?)]" + "\u201d\u2019":
        return False
    if prev_piece[-1] in "(" + "\u201c-" + "\u2014\u2013":
        return False
    return True


def row_plain(segs):
    parts = []
    for s in segs:
        t = clean(s["text"])
        if not t:
            continue
        if parts and glue_needed(parts[-1], t[0]):
            parts.append(" " + t)
        else:
            parts.append(t)
    return "".join(parts)


def is_sup_marker(seg, body_size):
    t = clean(seg["text"])
    if not re.fullmatch(r"[0-9]{1,3}|[ivxlcdm]{1,7}", t):
        return False
    return seg["size"] <= body_size * 0.75


def segs_html(segs, body_size, marker_maker=None):
    out = []
    for seg in segs:
        t = clean(seg["text"])
        if not t:
            continue
        if is_sup_marker(seg, body_size):
            a = marker_maker(t, seg) if marker_maker is not None else None
            if a is not None:
                out.append(a)
            else:
                out.append("<sup>" + esc(t) + "</sup>")
            continue
        if seg["italic"]:
            piece = "<i>" + esc(t) + "</i>"
        elif seg["bold"]:
            piece = "<b>" + esc(t) + "</b>"
        else:
            piece = esc(t)
        if out:
            out.append(" " + piece if glue_needed(out[-1], t[0]) else piece)
        else:
            out.append(piece)
    return "".join(out)


# ===========================================================================
#  Extração de linhas visuais
# ===========================================================================

def page_rows(page):
    spans = []
    try:
        d = page.get_text("dict", sort=True)
    except Exception:
        return []
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                t = s.get("text", "")
                if not t.strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                spans.append({
                    "text": t, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "size": s.get("size", 0.0), "cy": (y0 + y1) / 2.0,
                    "italic": "Italic" in s.get("font", ""),
                    "bold": "Bold" in s.get("font", ""),
                })
    spans.sort(key=lambda s: (s["cy"], s["x0"]))
    rows = []
    for s in spans:
        if rows and abs(rows[-1]["cy"] - s["cy"]) <= 6.0:
            r = rows[-1]
            r["segs"].append(s)
            r["y0"] = min(r["y0"], s["y0"])
            r["y1"] = max(r["y1"], s["y1"])
            r["x0"] = min(r["x0"], s["x0"])
            r["x1"] = max(r["x1"], s["x1"])
            r["size"] = max(r["size"], s["size"])
            r["cy"] = (r["cy"] * r["n"] + s["cy"]) / (r["n"] + 1)
            r["n"] += 1
        else:
            rows.append({
                "y0": s["y0"], "y1": s["y1"], "x0": s["x0"], "x1": s["x1"],
                "size": s["size"], "cy": s["cy"], "n": 1, "segs": [s],
            })
    for r in rows:
        r["segs"].sort(key=lambda s: s["x0"])
        r["text"] = row_plain(r["segs"])
    rows.sort(key=lambda r: r["cy"])
    return rows


def page_images(page):
    out = []
    try:
        for im in page.get_images(full=True):
            xref, smask, w, h = im[0], im[1], im[2], im[3]
            if w < 100 or h < 100 or w * h < 15000:
                continue
            for rect in page.get_image_rects(xref):
                out.append({"y0": rect.y0, "x0": rect.x0, "xref": xref})
    except Exception:
        pass
    if not out:
        try:
            info = page.get_image_info()
        except Exception:
            info = []
        for im in info:
            w, h = im.get("width") or 0, im.get("height") or 0
            if w < 100 or h < 100 or w * h < 15000:
                continue
            b = im.get("bbox") or (0, 0, 0, 0)
            out.append({"y0": b[1], "x0": b[0], "xref": im.get("xref")})
    out.sort(key=lambda i: (i["y0"], i["x0"]))
    return out


# ===========================================================================
#  Cabeçalhos / rodapés correntes
# ===========================================================================

def zone_of(cy, page_h):
    if page_h <= 0:
        return None
    f = cy / page_h
    if f < 0.075:
        return "top"
    if f > 0.93:
        return "bottom"
    return None


def detect_running_lines(rows_per_page, pages_h):
    n = len(rows_per_page)
    counts = Counter()
    for rows, h in zip(rows_per_page, pages_h):
        for r in rows:
            z = zone_of(r["cy"], h)
            if not z or not r["text"] or len(r["text"]) > 90:
                continue
            counts[(z, r["text"])] += 1
    thr = max(3, int(n * 0.2)) if n else 0
    return {k for k, c in counts.items() if c >= thr}


def is_page_number_row(r, page_h):
    t = r["text"]
    if not re.fullmatch(r"[IVXLCDM]{1,8}|\d{1,4}", t):
        return False
    f = r["cy"] / page_h if page_h else 0
    return f > 0.86 or f < 0.08


def content_rows(rows, page_h, running_lines):
    out = []
    for r in rows:
        if not r["text"]:
            continue
        z = zone_of(r["cy"], page_h)
        if z and (z, r["text"]) in running_lines:
            continue
        if is_page_number_row(r, page_h):
            continue
        out.append(r)
    return out


# ===========================================================================
#  Geometria do documento
# ===========================================================================

def analyse_geometry(all_content_rows, pages_h):
    geo = {"body_size": 11.0, "left": 72.0, "right": 540.0, "centre": 306.0,
           "width": 468.0, "line_gap": 14.0, "page_h": max(pages_h) if pages_h else 792}
    all_rows = [r for lst in all_content_rows for r in lst]
    if not all_rows:
        return geo
    sizes = Counter()
    for r in all_rows:
        sizes[round(r["size"], 1)] += len(r["text"])
    geo["body_size"] = sizes.most_common(1)[0][0]
    body = [r for r in all_rows if abs(r["size"] - geo["body_size"]) <= 1.2]
    if not body:
        body = all_rows
    xs = Counter()
    x1s = []
    for r in body:
        xs[round(r["x0"] / 4) * 4] += 1
        x1s.append(r["x1"])
    geo["left"] = xs.most_common(1)[0][0]
    x1s.sort()
    geo["right"] = x1s[min(len(x1s) - 1, int(len(x1s) * 0.92))]
    geo["width"] = max(geo["right"] - geo["left"], 50)
    geo["centre"] = (geo["left"] + geo["right"]) / 2
    gaps = []
    for rows in all_content_rows:
        prev = None
        for r in rows:
            if abs(r["size"] - geo["body_size"]) > 1.2:
                continue
            if prev is not None:
                d = r["cy"] - prev
                if 0 < d < geo["page_h"] * 0.5:
                    gaps.append(d)
            prev = r["cy"]
    if gaps:
        geo["line_gap"] = median(gaps)
    first_ys = Counter()
    for rows in all_content_rows:
        if len(rows) >= 6:
            first_ys[round(rows[0]["y0"])] += 1
    geo["top_margin"] = first_ys.most_common(1)[0][0] if first_ys else 72.0
    return geo


# ===========================================================================
#  Classificação de linhas (título / verso / corpo)
# ===========================================================================

def classify_rows(rows, geo):
    """Devolve lista de etiquetas: 'normal', 'h1', 'h2' ou 'verso'."""
    n = len(rows)
    labels = ["normal"] * n
    sent_end = ".!?" + "\u2026\u201d\u2019"
    lw = geo["width"]

    def is_short(r):
        L = len(r["text"])
        return 1 <= L <= 110

    def end_punct(t):
        return bool(t) and t[-1] in sent_end

    def centred(r):
        c = (r["x0"] + r["x1"]) / 2
        return abs(c - geo["centre"]) < max(0.10 * lw, 14)

    def span_frac(r):
        return (r["x1"] - r["x0"]) / max(lw, 1)

    def strong(r):
        return any(s["bold"] for s in r["segs"]) or r["size"] >= geo["body_size"] + 0.9

    def short_centre(r):
        return (is_short(r) and centred(r) and span_frac(r) <= 0.6)

    for i, r in enumerate(rows):
        t = r["text"]
        if not is_short(r):
            continue
        prev = rows[i - 1] if i > 0 else None
        nxt = rows[i + 1] if i < n - 1 else None
        bold = any(s["bold"] for s in r["segs"])
        bigger = r["size"] >= geo["body_size"] + 0.9
        much_bigger = r["size"] >= geo["body_size"] + 2.0
        c = centred(r) and span_frac(r) <= 0.6
        gap_before = 0.0 if prev is None else r["y0"] - prev["y1"]
        if prev is None:
            gap_before = 1e9          # primeira linha da página
        if end_punct(t) and len(t) > 40:
            continue
        if not (bold or bigger or c):
            continue
        if not (bold or bigger) and c and span_frac(r) >= 0.6:
            continue
        if end_punct(t) and not (bold or bigger) and not much_bigger:
            continue
        if strong(r) and short_centre(r) and not bold:
            if not (gap_before >= 1.6 * geo["line_gap"]):
                continue
        prev_short_centre = (prev is not None and labels[i - 1] == "verso"
                             or (prev is not None and not strong(prev)
                                 and short_centre(prev)
                                 and r["y0"] - prev["y1"] < 1.5 * geo["line_gap"]))
        nxt_short_centre = (nxt is not None and not strong(nxt)
                            and short_centre(nxt)
                            and nxt["y0"] - r["y1"] < 1.5 * geo["line_gap"])
        if (not bold and not bigger and not much_bigger) and (prev_short_centre or nxt_short_centre):
            labels[i] = "verso"
            continue
        if not (bold or bigger):
            if not (c and gap_before >= 1.6 * geo["line_gap"]):
                continue
            labels[i] = "h2"
            continue
        # bold ou maior
        if (not bold) and bigger and span_frac(r) >= 0.5:
            continue
        if end_punct(t) and span_frac(r) >= 0.45 and not much_bigger:
            continue
        if much_bigger or (bold and bigger) or (bold and gap_before >= 1.4 * geo["line_gap"]):
            labels[i] = "h1"
        else:
            labels[i] = "h2"
    return labels


# ===========================================================================
#  Páginas isoladas (epígrafes / dedicatórias) e aberturas de capítulo
# ===========================================================================

def is_heading_like(t):
    t2 = re.sub(r"\s+", " ", t).strip()
    if re.match(r"^(?:cap[ií]tulo|parte|sec[cç][aã]o|livro|cap\.|part\.)\b",
                t2, re.I):
        return True
    return bool(t2) and t2 == t2.upper()


def is_dedication_line(r, geo):
    """Linha única, curta e não encostada à margem esquerda (centrada)."""
    lw = max(geo["width"], 1)
    sf = (r["x1"] - r["x0"]) / lw
    indented = r["x0"] > geo["left"] + max(6.0, 0.08 * lw)
    return indented and sf <= 0.75


def detect_epigraph_page(cre, geo):
    """Página que contém apenas uma epígrafe ou dedicatória.

    Devolve "dedicatoria", "epigrafe" ou None.
    """
    if not cre:
        return None
    n = len(cre)
    if n > 8:
        return None
    if not all(1 <= len(r["text"]) <= 110 for r in cre):
        return None
    if any(r["size"] > geo["body_size"] + 0.6 for r in cre):
        return None
    if sum(len(r["text"]) for r in cre) > 260:
        return None
    small = any(r["size"] <= geo["body_size"] - 1.0 for r in cre)
    if small:
        return "epigrafe"
    if n == 1 and is_dedication_line(cre[0], geo) and not is_heading_like(cre[0]["text"]):
        return "dedicatoria"
    return None


def is_chapter_opener(cre, geo):
    """Abre um capítulo a página que começa com muito espaço em branco
    (a quebra de página indica o fim do capítulo anterior)."""
    if not cre:
        return False
    first = cre[0]
    blank = first["y0"] - geo.get("top_margin", 72.0)
    return blank >= max(2.0 * geo["line_gap"], 30)


# ===========================================================================
#  Construção do fluxo de conteúdo
# ===========================================================================

class Flow:
    def __init__(self, geo):
        self.geo = geo
        self.items = []
        self._para = None
        self._verso = None

    def _flush_para(self):
        if self._verso is not None:
            self.items.append({"kind": "para", "cls": "verso",
                               "html": "".join(self._verso["html"]),
                               "page": self._verso["page"]})
            self._verso = None
        if self._para is not None:
            if self._para["html"]:
                self.items.append({"kind": "para",
                                   "cls": self._para["cls"],
                                   "html": "".join(self._para["html"]),
                                   "page": self._para["page"]})
            self._para = None

    def heading(self, title, level, page):
        self._flush_para()
        self.items.append({"kind": "head", "title": title, "level": level,
                           "page": page})

    def fim(self, title, page):
        self._flush_para()
        self.items.append({"kind": "fim", "html": title, "page": page})

    def epigrafe(self, html_body, cls, page):
        self._flush_para()
        self.items.append({"kind": "epigrafe", "cls": cls,
                           "html": html_body, "page": page})

    def note(self, html_body, page):
        self._flush_para()
        self.items.append({"kind": "note", "html": html_body, "page": page})

    def image(self, html_body, page):
        self._flush_para()
        self.items.append({"kind": "image", "html": html_body, "page": page})

    def line(self, html_body, x0, y0, x1, ends_punct, first, gap, page):
        geo = self.geo
        if self._verso is not None:
            self._flush_para()
        if self._para is None:
            noind = x0 < geo["left"] + max(4.0, 0.015 * geo["width"])
            self._para = {"html": [], "cls": "noindent" if noind else "",
                          "page": page, "last": None}
        elif self._para["html"]:
            prev = self._para["last"]
            boundary = False
            if x0 > geo["left"] + max(6.0, 0.02 * geo["width"]):
                boundary = True
            elif not first and gap > 1.5 * geo["line_gap"]:
                boundary = True
            elif (prev is not None and prev[2]
                    and prev[1] < geo["right"] - 0.35 * geo["width"]
                    and x0 < geo["left"] + max(4.0, 0.02 * geo["width"])):
                boundary = True
            if boundary:
                self._flush_para()
                self._para = {"html": [], "cls": "", "page": page, "last": None}
        self._para["html"].append(html_body if not self._para["html"] else " " + html_body)
        self._para["last"] = (y0, x1, ends_punct)
        self._para["page"] = page

    def verso(self, html_body, y0, page):
        if self._verso is None or self._verso["page"] != page:
            self._flush_para()
            self._verso = {"html": [], "page": page}
        self._verso["html"].append(html_body if not self._verso["html"] else "<br/>" + html_body)

    def close(self):
        self._flush_para()


# ===========================================================================
#  Partição em ficheiros (capítulos)
# ===========================================================================

def split_footnotes(rows, geo):
    notes = []
    for r in rows:
        segs = r["segs"]
        first = segs[0] if segs else None
        tfirst = clean(first["text"]) if first is not None else ""
        if (first is not None and is_sup_marker(first, geo["body_size"])
                and re.fullmatch(r"[0-9]+|[ivxlcdm]+", tfirst)):
            notes.append({"num": tfirst, "rows": [r]})
        else:
            if notes:
                notes[-1]["rows"].append(r)
            else:
                notes.append({"num": "", "rows": [r]})
    out = []
    for nt in notes:
        pieces = []
        for r in nt["rows"]:
            pieces.append(segs_html(r["segs"], geo["body_size"], lambda a, b: ""))
        body = " ".join(x for x in pieces if x.strip()).strip()
        if nt["num"]:
            body = "<span class=\"notanum\">" + esc(nt["num"]) + ".</span> " + body
        out.append((nt["num"], body))
    return out


def split_head_groups(items):
    files = []
    cur = None
    prev_head = False
    ch_seq = [0]
    epi_seq = [0]

    def mk():
        return {"title": None, "blocks": [], "children": [], "kind": "headfile"}

    for it in items:
        if it["kind"] == "head":
            if prev_head and cur is not None and cur["kind"] == "headfile" and cur["title"] is not None:
                ch_seq[0] += 1
                hid = "cap%d" % ch_seq[0]
                cur["children"].append((hid, it["title"]))
                cur["blocks"].append(("h2", hid, esc(it["title"]), it["page"]))
            else:
                cur = mk()
                cur["title"] = it["title"]
                files.append(cur)
                cur["blocks"].append(("h1", esc(it["title"]), it["page"]))
            prev_head = True
            continue
        if it["kind"] == "epigrafe":
            if it["cls"] == "dedicatoria":
                title = "Dedicatória"
            else:
                epi_seq[0] += 1
                title = "Epígrafe" if epi_seq[0] == 1 else "Epígrafe %s" % to_roman(epi_seq[0])
            cur = mk()
            cur["title"] = title
            files.append(cur)
            cur["blocks"].append(("p", it["cls"], it["html"], it["page"]))
            prev_head = False
            continue
        if cur is None:
            cur = mk()
            cur["title"] = "Início"
            files.append(cur)
        prev_head = False
        if it["kind"] == "para":
            cur["blocks"].append(("p", it["cls"], it["html"], it["page"]))
        elif it["kind"] == "note":
            cur["blocks"].append(("note", it["html"], it["page"]))
        elif it["kind"] == "image":
            cur["blocks"].append(("image", it["html"], it["page"]))
        elif it["kind"] == "fim":
            cur["blocks"].append(("fim", esc(it["html"]), it["page"]))
    return files


def apply_noheading_chunks(files, pages_total, chunk):
    if len(files) != 1 or chunk <= 0:
        return files
    b = files[0]
    if not b["blocks"] or pages_total <= chunk:
        return files
    out = []
    groups = {}
    for blk in b["blocks"]:
        page = blk[3] if len(blk) > 3 else 1
        bucket = max(1, (page - 1) // chunk + 1)
        groups.setdefault(bucket, []).append(blk)
    keys = sorted(groups)
    for idx, k in enumerate(keys):
        page0 = (k - 1) * chunk + 1
        page1 = min(k * chunk, pages_total)
        title = "Páginas %d–%d" % (page0, page1)
        out.append({"title": title, "blocks": groups[k], "children": [],
                    "kind": "chunk"})
    return out


# ===========================================================================
#  Escrita do EPUB
# ===========================================================================

CSS = """body { font-family: "Times New Roman", Georgia, serif; line-height: 1.5; }
h1 { text-align: center; font-weight: bold; margin: 1.5em 0 0.9em 0; font-size: 1.35em;
     page-break-before: always; }
h1.brk0 { page-break-before: auto; }
h2 { text-align: center; font-weight: normal; margin: 1.7em 0 1em 0; font-size: 1.12em; }
p { text-align: justify; text-indent: 1.5em; margin: 0; }
p.noindent { text-indent: 0; }
p.verso { text-align: center; text-indent: 0; margin: 0.15em 0; }
p.epigrafe { text-align: center; font-style: italic; margin: 3em 1.5em; page-break-before: always; }
p.dedicatoria { text-align: center; margin: 5em 1.5em; page-break-before: always; }
p.nota { font-size: 0.85em; margin: 0.2em 0 1em 1.2em; text-indent: -1.2em; }
span.notanum { font-weight: bold; }
figure { margin: 0.8em 0; text-align: center; }
figure img { max-width: 100%; height: auto; }
.coverpage { text-align: center; }
.coverpage img { max-width: 100%; max-height: 100%; }
"""

DOC_HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}">
<head>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
"""
DOC_TAIL = "\n</body>\n</html>\n"


def blocks_to_html(blocks):
    out = []
    for b in blocks:
        kind = b[0]
        if kind == "h1":
            out.append("<h1>" + b[1] + "</h1>")
        elif kind == "h2":
            out.append("<h2 id=\"%s\">%s</h2>" % (b[1], b[2]))
        elif kind == "p":
            cls = b[1]
            out.append("<p%s>%s</p>" % ((" class=\"%s\"" % cls) if cls else "", b[2]))
        elif kind == "note":
            out.append("<p class=\"nota\">%s</p>" % b[1])
        elif kind == "fim":
            out.append("<p class=\"fim\">%s</p>" % b[1])
        elif kind == "image":
            out.append(b[1])
    return "\n".join(out)


def render_xhtml_file(path, title, blocks, lang):
    body_inner = blocks_to_html(blocks)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(DOC_HEAD.format(title=esc(title), lang=lang) + body_inner + DOC_TAIL)


def nav_xhtml(files, title, lang, cover=True):
    rows = ["<nav epub:type=\"toc\"><h1>Índice</h1><ol>"]
    for f in files:
        lbl = f["title"] if f["title"] else title
        rows.append("<li><a href=\"%s\">%s</a>" % (f["fname"], esc(lbl)))
        if f["children"]:
            rows.append("<ol>")
            for hid, htitle in f["children"]:
                rows.append("<li><a href=\"%s#%s\">%s</a></li>"
                            % (f["fname"], hid, esc(htitle)))
            rows.append("</ol>")
        rows.append("</li>")
    rows.append("</ol></nav>")
    rows.append("<nav epub:type=\"landmarks\" hidden=\"hidden\"><ol>")
    if cover:
        rows.append("<li><a epub:type=\"cover\" href=\"cover.xhtml\">Capa</a></li>")
    start = files[0]["fname"] if files else "nav.xhtml"
    rows.append("<li><a epub:type=\"bodymatter\" href=\"%s\">Início</a></li>" % start)
    rows.append("</ol></nav>")
    doc = (DOC_HEAD.format(title=esc(title), lang=lang) + "\n".join(rows) + DOC_TAIL)
    return doc


def write_content_opf(path, title, author, lang, files, has_cover):
    items = []
    items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    items.append('<item id="css" href="style.css" media-type="text/css"/>')
    spine = []
    if has_cover:
        items.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        items.append('<item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image"/>')
        spine.append("cover")
    for i, f in enumerate(files, start=1):
        sid = "sec%d" % i
        items.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (sid, f["fname"]))
        spine.append(sid)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta = ['<dc:identifier id="pub-id">urn:uuid:%s</dc:identifier>' % uuid.uuid4(),
            '<dc:title>%s</dc:title>' % esc(title),
            '<dc:language>%s</dc:language>' % esc(lang)]
    if author:
        meta.append('<dc:creator id="creator">%s</dc:creator>' % esc(author))
    meta.append('<meta property="dcterms:modified">%s</meta>' % now)
    if has_cover:
        meta.append('<meta name="cover" content="cover-image"/>')
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="pub-id" xml:lang="%s">\n' % esc(lang) +
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' +
           "\n".join(meta) + "\n</metadata>\n<manifest>\n" +
           "\n".join(items) + "\n</manifest>\n<spine>\n" +
           "\n".join('<itemref idref="%s"/>' % s for s in spine) +
           "\n</spine>\n</package>\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(opf)


def zip_epub(build_dir, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)
    mt = os.path.join(build_dir, "mimetype")
    with open(mt, "w") as fh:
        fh.write("application/epub+zip")
    with zipfile.ZipFile(out_path, "w") as zf:
        zf.write(mt, "mimetype", compress_type=zipfile.ZIP_STORED)
        zf.write(os.path.join(build_dir, "META-INF", "container.xml"),
                 "META-INF/container.xml", compress_type=zipfile.ZIP_DEFLATED)
        for root, _, fnames in os.walk(os.path.join(build_dir, "OEBPS")):
            for fn in sorted(fnames):
                p = os.path.join(root, fn)
                arc = os.path.relpath(p, build_dir).replace("\\", "/")
                zf.write(p, arc, compress_type=zipfile.ZIP_DEFLATED)


# ===========================================================================
#  Pipeline principal
# ===========================================================================

def convert(pdf_path, out_path, opts, progress_cb=None):
    """Converte um PDF em EPUB.

    Args:
        pdf_path: caminho do PDF de entrada.
        out_path: caminho do EPUB de saída.
        opts: objeto com atributos titulo/autor/lingua/chunk_paginas/nao_dividir.
        progress_cb: callback opcional pagina_atual, total, mensagem.
            Quando None (CLI), usa print() como antes.

    Raises:
        PDFError: em erros de domínio (sem pymupdf, sem páginas, sem texto).
    """
    def emit(page, total, msg):
        if progress_cb is not None:
            try:
                progress_cb(page, total, msg)
            except Exception:
                pass
        else:
            print(msg)

    if pymupdf is None:
        raise PDFError("Erro: é necessário instalar a biblioteca PyMuPDF "
                       "(pip install pymupdf).")
    doc = pymupdf.open(pdf_path)
    npages = doc.page_count
    emit(0, npages, "Páginas: %d" % npages)
    if npages == 0:
        raise PDFError("Erro: PDF sem páginas.")

    title = opts.titulo or (doc.metadata or {}).get("title") or \
        os.path.splitext(os.path.basename(pdf_path))[0]
    author = opts.autor or (doc.metadata or {}).get("author") or ""
    lang = opts.lingua
    chunk = opts.chunk_paginas
    if getattr(opts, "nao_dividir", False):
        chunk = 0

    pages_h = []
    rows_per_page = []
    for i in range(npages):
        page = doc[i]
        pages_h.append(page.rect.height)
        rows_per_page.append(page_rows(page))
        if progress_cb is not None and (i + 1) % 10 == 0:
            emit(i + 1, npages, "A ler páginas: %d/%d" % (i + 1, npages))

    total_text = sum(len(r["text"]) for rows in rows_per_page for r in rows)
    if total_text < 60:
        raise PDFError(
            "Erro: o PDF não parece conter texto extraível "
            "(é um PDF digitalizado?).")

    running = detect_running_lines(rows_per_page, pages_h)
    all_content_rows = []
    for rows, h in zip(rows_per_page, pages_h):
        all_content_rows.append(content_rows(rows, h, running))
    geo = analyse_geometry(all_content_rows, pages_h)
    emit(0, npages,
         "Corpo: %.1f pt | margens %.0f–%.0f | linha %.1f pt"
         % (geo["body_size"], geo["left"], geo["right"], geo["line_gap"]))

    # incluir ou não a 1.ª página no fluxo (a 1.ª página é sempre a capa)
    words_p1 = len(re.findall(r"\S+", doc[0].get_text("text")))
    include_p1 = words_p1 >= 60
    first_flow = 0 if include_p1 else 1

    flow = Flow(geo)
    img_files = {}
    img_seq = [0]
    chap_no = [0]

    # --- diretório de trabalho ---
    build = os.path.join(os.path.dirname(out_path), ".pdf2epub_build")
    meta_dir = os.path.join(build, "META-INF")
    oebps = os.path.join(build, "OEBPS")
    img_dir = os.path.join(oebps, "images")
    for d in (build, meta_dir, oebps, img_dir):
        os.makedirs(d, exist_ok=True)

    def ensure_image(xref):
        if not xref or xref in img_files:
            return img_files.get(xref)
        img_seq[0] += 1
        try:
            info = doc.extract_image(xref)
        except Exception:
            return None
        ext = info.get("ext") or "png"
        name = "img%d.%s" % (img_seq[0], ext)
        with open(os.path.join(img_dir, name), "wb") as fh:
            fh.write(info["image"])
        img_files[xref] = name
        return name

    for pno in range(first_flow, npages):
        if progress_cb is not None:
            emit(pno + 1, npages, "A converter página %d/%d" % (pno + 1, npages))
        page = doc[pno]
        h = pages_h[pno]
        rows = rows_per_page[pno]
        cre = content_rows(rows, h, running)
        labels = classify_rows(cre, geo)
        imgs = page_images(page) if not (pno == 0 and include_p1) else []

        epi = detect_epigraph_page(cre, geo)
        if epi:
            parts = []
            for r in cre:
                parts.append(segs_html(r["segs"], geo["body_size"]))
            flow.epigrafe("<br/>".join(parts), epi, pno + 1)
            continue
        if cre and is_chapter_opener(cre, geo) and not any(
                labels[k] in ("h1", "h2") for k in range(min(3, len(labels)))):
            chap_no[0] += 1
            flow.heading("Capítulo " + to_roman(chap_no[0]), 1, pno + 1)

        last_body_idx = -1
        for i, r in enumerate(cre):
            if r["size"] >= geo["body_size"] - 1.0:
                last_body_idx = i
        note_rows = []
        if last_body_idx >= 0:
            for i, r in enumerate(cre):
                if i > last_body_idx and r["size"] < geo["body_size"] - 1.2:
                    note_rows.append(r)
        body_idx = [i for i in range(len(cre)) if cre[i] not in note_rows]

        events = []
        img_it = iter(imgs)
        nxt_img = next(img_it, None)
        for i in body_idx:
            r = cre[i]
            while nxt_img is not None and nxt_img["y0"] < r["y0"]:
                name = ensure_image(nxt_img["xref"])
                if name:
                    events.append({"kind": "img", "y": nxt_img["y0"], "html":
                                   '<figure><img src="images/%s" alt=""/></figure>' % name})
                nxt_img = next(img_it, None)
            lab = labels[i]
            events.append({"kind": lab, "r": r})
        while nxt_img is not None:
            name = ensure_image(nxt_img["xref"])
            if name:
                events.append({"kind": "img", "y": nxt_img["y0"], "html":
                               '<figure><img src="images/%s" alt=""/></figure>' % name})
            nxt_img = next(img_it, None)
        events.sort(key=lambda e: (e.get("r", {}).get("y0", e.get("y", 0)),))

        prev_cy = None
        for ev in events:
            if ev["kind"] == "img":
                flow.image(ev["html"], pno + 1)
                continue
            r = ev["r"]
            t = r["text"]
            first_ev = prev_cy is None
            gap = 0.0 if prev_cy is None else r["cy"] - prev_cy
            if ev["kind"] in ("h1", "h2"):
                if re.fullmatch(r"(?:FIM|FIN|FINE|END|THE\s+END|FINIS)", t, re.I):
                    flow.fim(t, pno + 1)
                else:
                    flow.heading(t, int(ev["kind"][1]), pno + 1)
            elif ev["kind"] == "verso":
                flow.verso(segs_html(r["segs"], geo["body_size"]), r["y0"], pno + 1)
            else:
                flow.line(segs_html(r["segs"], geo["body_size"]),
                          r["x0"], r["y0"], r["x1"],
                          bool(t) and t[-1] in ".!?" + "\u2026\u201d\u2019",
                          first_ev, gap, pno + 1)
            prev_cy = r["cy"]

        if note_rows:
            for num, body in split_footnotes(note_rows, geo):
                if body:
                    flow.note(body, pno + 1)

    flow.close()

    # imagens da página 1 quando esta entra no fluxo
    items = flow.items
    has_head = any(it["kind"] == "head" for it in items)
    files = split_head_groups(items)
    if not has_head:
        files = apply_noheading_chunks(files, npages, chunk or 300)

    fnames = []
    for idx, f in enumerate(files, start=1):
        nm = "cap%03d.xhtml" % idx if has_head else "parte%03d.xhtml" % idx
        f["fname"] = nm
        fnames.append(nm)

    make_cover(doc, img_dir)
    if include_p1:
        pass  # imagens da página 1 já foram processadas dentro do ciclo

    # cover.xhtml
    with open(os.path.join(oebps, "cover.xhtml"), "w", encoding="utf-8") as fh:
        body = '<div class="coverpage"><img src="images/cover.png" alt="Capa"/></div>'
        fh.write(DOC_HEAD.format(title=esc(title), lang=lang) + body + DOC_TAIL)
    for f in files:
        render_xhtml_file(os.path.join(oebps, f["fname"]), f["title"] or title,
                          f["blocks"], lang)
    with open(os.path.join(oebps, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    nav = nav_xhtml(files, title, lang)
    with open(os.path.join(oebps, "nav.xhtml"), "w", encoding="utf-8") as fh:
        fh.write(nav)
    write_content_opf(os.path.join(oebps, "content.opf"), title, author, lang,
                      files, True)
    with open(os.path.join(meta_dir, "container.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<container version="1.0" '
                 'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles>\n'
                 '<rootfile full-path="OEBPS/content.opf" '
                 'media-type="application/oebps-package+xml"/>\n'
                 '</rootfiles>\n</container>\n')

    zip_epub(build, out_path)
    import shutil
    shutil.rmtree(build, ignore_errors=True)
    emit(npages, npages, "Criado: %s" % out_path)


def make_cover(doc, img_dir):
    page = doc[0]
    r = page.rect
    target = 1600.0
    scale = max(1.0, min(target / max(r.width, r.height), target / min(r.width, r.height)))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
    pix.save(os.path.join(img_dir, "cover.png"))


# ===========================================================================
#  CLI
# ===========================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pdf2epub",
        description="Converte um PDF de texto para EPUB 3 (a primeira página "
                    "do PDF é usada como capa do EPUB).")
    ap.add_argument("pdf", help="ficheiro PDF de entrada")
    ap.add_argument("-o", "--saida", help="ficheiro EPUB de saída "
                    "(predefinição: mesmo nome do PDF com extensão .epub)")
    ap.add_argument("--titulo", help="título do livro (por omissão usa o "
                    "metadado do PDF ou o nome do ficheiro)")
    ap.add_argument("--autor", help="autor do livro (por omissão usa o "
                    "metadado do PDF)")
    ap.add_argument("--lingua", default="pt", help="código da língua do "
                    "conteúdo (predefinição: pt)")
    ap.add_argument("--nao-dividir", action="store_true",
                    help="não divide documentos sem títulos em vários "
                    "ficheiros de tamanho reduzido")
    ap.add_argument("--paginas-por-ficheiro", type=int, default=300,
                    dest="chunk_paginas",
                    help="documentos sem títulos: páginas por ficheiro "
                    "(predefinição: 300)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        sys.stderr.write("Erro: ficheiro não encontrado: %s\n" % args.pdf)
        sys.exit(1)
    out = args.saida or os.path.splitext(args.pdf)[0] + ".epub"
    if args.nao_dividir:
        args.chunk = 0
    try:
        convert(args.pdf, out, args)
    except PDFError as e:
        # Mantém o comportamento antigo da CLI (mensagem + exit 1/2)
        # sem encerrar o processo quando usado como biblioteca pela GUI.
        msg = str(e)
        sys.stderr.write(msg + "\n")
        if "PyMuPDF" in msg:
            sys.exit(2)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    return 0


if __name__ == "__main__":
    sys.exit(main())

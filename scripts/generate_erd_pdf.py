#!/usr/bin/env python3
"""
Gera um ERD textual (PDF) e um diagrama Mermaid a partir dos models Django.

Saídas:
- docs/erd.pdf
- docs/ERD.mmd

Não requer dependências extras: o PDF é gerado manualmente via sintaxe mínima.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import List, Tuple, Dict


def setup_django():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(os.path.join(base_dir, os.pardir))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sisalvweb.settings")
    # Stub de whitenoise quando não instalado (para permitir django.setup())
    try:
        import whitenoise  # type: ignore
    except Exception:
        import types
        wn = types.ModuleType('whitenoise')
        wn.__file__ = __file__
        wn_r = types.ModuleType('whitenoise.runserver_nostatic')
        wn_r.__file__ = __file__
        sys.modules['whitenoise'] = wn
        sys.modules['whitenoise.runserver_nostatic'] = wn_r

    # Stub básico de PIL/Image quando Pillow não está instalado (apenas para import-time)
    try:
        from PIL import Image  # type: ignore
    except Exception:
        import types as _types
        class _StubImage:
            @staticmethod
            def open(_):
                raise RuntimeError("Pillow (PIL) não disponível neste ambiente.")
        pil = _types.ModuleType('PIL')
        pil.__file__ = __file__
        pil_img = _types.ModuleType('PIL.Image')
        pil_img.__file__ = __file__
        pil.Image = _StubImage
        sys.modules['PIL'] = pil
        sys.modules['PIL.Image'] = pil_img
        sys.modules['PIL'].Image = _StubImage

    import django
    django.setup()


def collect_models_info():
    from django.apps import apps as django_apps
    from django.db import models as djm

    def model_label(m):
        return f"{m._meta.app_label}.{m.__name__}"

    entities: Dict[str, Dict] = {}
    relations: List[Tuple[str, str, str, str]] = []  # (src_model, rel_type, dst_model, via)

    for app_config in django_apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue
        for m in app_config.get_models():
            label = model_label(m)
            fields = []
            pk_name = m._meta.pk and m._meta.pk.name or "id"
            db_table = getattr(m._meta, "db_table", "") or m._meta.label_lower.replace(".", "_")

            # Campos simples e FKs
            for f in m._meta.get_fields():
                # Skip reverse relations in this pass
                if f.auto_created and not f.concrete:
                    continue
                if hasattr(f, "remote_field") and getattr(f.remote_field, "model", None) is not None and f.many_to_one:
                    tgt = f.remote_field.model
                    tgt_label = model_label(tgt)
                    fields.append((f.name, f.__class__.__name__, f"FK->{tgt.__name__}"))
                    relations.append((label, "N:1", tgt_label, f.name))
                elif hasattr(f, "many_to_many") and f.many_to_many and hasattr(f, "remote_field"):
                    # M2M declared on this model
                    tgt = f.remote_field.model
                    tgt_label = model_label(tgt)
                    fields.append((f.name, f.__class__.__name__, f"M2M->{tgt.__name__}"))
                    relations.append((label, "N:N", tgt_label, f.name))
                else:
                    ftype = getattr(f, "get_internal_type", lambda: f.__class__.__name__)()
                    note = "PK" if f.name == pk_name else ""
                    fields.append((f.name, ftype, note))

            entities[label] = {
                "name": m.__name__,
                "app": m._meta.app_label,
                "db_table": db_table,
                "fields": fields,
            }

    # Dedup relations (keep a single direction record for N:N)
    rel_set = set()
    final_relations: List[Tuple[str, str, str, str]] = []
    for a, t, b, via in relations:
        key = (a, t, b, via)
        if t == "N:N":
            undirected = tuple(sorted([a, b])) + (t,)
            if undirected in rel_set:
                continue
            rel_set.add(undirected)
            final_relations.append((a, t, b, via))
        else:
            if key in rel_set:
                continue
            rel_set.add(key)
            final_relations.append((a, t, b, via))

    return entities, final_relations


# -------------------- Mermaid ER --------------------
def write_mermaid(entities: Dict[str, Dict], relations: List[Tuple[str, str, str, str]], out_path: str):
    def er_name(full_label: str) -> str:
        app, model = full_label.split(".")
        return f"{app}_{model}"

    lines: List[str] = ["erDiagram"]
    # Entities with fields
    for full_label, ent in sorted(entities.items()):
        name = er_name(full_label)
        lines.append(f"  {name} {{")
        for fname, ftype, note in ent["fields"]:
            t = (ftype or "Field")
            label = f"{t} {fname}"
            if note:
                label += f" \"{note}\""
            lines.append(f"    {label}")
        lines.append("  }")

    # Relationships
    def card(symbol: str) -> str:
        if symbol == "N:1":
            return "}o--||"
        if symbol == "1:1":
            return "||--||"
        if symbol == "N:N":
            return "}o--o{"
        return "}o--||"

    for a, t, b, via in sorted(relations):
        A = er_name(a)
        B = er_name(b)
        lines.append(f"  {A} {card(t)} {B} : {via}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -------------------- Minimal PDF --------------------
class MiniPDF:
    def __init__(self, page_w=595, page_h=842, margin=40, font_size=10):
        self.page_w = page_w
        self.page_h = page_h
        self.margin = margin
        self.font_size = font_size
        self.lines: List[str] = []

    @staticmethod
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def add_line(self, text: str):
        # Store plain text lines; we'll layout later
        self.lines.append(text.replace("\r", "").rstrip("\n"))

    def build(self) -> bytes:
        # Build a one-page PDF laying out lines top-down
        content = []
        top = self.page_h - self.margin
        leading = self.font_size + 3
        x = self.margin
        y = top
        content.append("BT")
        content.append(f"/F1 {self.font_size} Tf")
        content.append(f"{x} {y} Td")
        first = True
        for line in self.lines:
            if not first:
                content.append(f"0 -{leading} Td")
            first = False
            content.append(f"({self._esc(line)}) Tj")
        content.append("ET")
        stream = ("\n".join(content) + "\n").encode("latin-1", errors="ignore")

        # Assemble objects
        parts: List[bytes] = []
        xref_offsets: List[int] = []

        def w(b: bytes):
            parts.append(b)

        def pos() -> int:
            return sum(len(p) for p in parts)

        w(b"%PDF-1.4\n")
        # 1: Catalog
        xref_offsets.append(pos())
        w(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        # 2: Pages
        xref_offsets.append(pos())
        w(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        # 3: Page
        xref_offsets.append(pos())
        w((
            "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ).format(w=self.page_w, h=self.page_h).encode("ascii"))
        # 4: Font
        xref_offsets.append(pos())
        w(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
        # 5: Contents
        xref_offsets.append(pos())
        w((f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n").encode("ascii"))
        w(stream)
        w(b"endstream\nendobj\n")

        # Xref
        xref_start = pos()
        w(b"xref\n")
        w((f"0 {len(xref_offsets)+1}\n").encode("ascii"))
        w(b"0000000000 65535 f \n")
        for off in xref_offsets:
            w((f"{off:010d} 00000 n \n").encode("ascii"))
        # Trailer
        w((
            "trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n"
        ).encode("ascii").replace(b"{size}", str(len(xref_offsets)+1).encode("ascii")).replace(b"{start}", str(xref_start).encode("ascii")))
        return b"".join(parts)


def write_pdf(entities: Dict[str, Dict], relations: List[Tuple[str, str, str, str]], out_path: str):
    pdf = MiniPDF(font_size=10)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    title = "SISALVWEB — Mapa de Entidades (ER)"
    pdf.add_line(title)
    pdf.add_line(f"Gerado em: {now}")
    pdf.add_line("")

    # Entidades
    pdf.add_line("Entidades:")
    for lbl, ent in sorted(entities.items()):
        hdr = f"- {ent['app']}.{ent['name']} [tabela: {ent['db_table']}]"
        pdf.add_line(hdr)
        # Campos (limitar para caber na página)
        for fname, ftype, note in ent["fields"][:30]:
            suffix = f" — {note}" if note else ""
            pdf.add_line(f"    · {fname}: {ftype}{suffix}")
        if len(ent["fields"]) > 30:
            pdf.add_line("    · …")
    pdf.add_line("")

    # Relacionamentos
    pdf.add_line("Relacionamentos:")
    def short(x: str) -> str:
        # apps.denuncias.Denuncia -> denuncias.Denuncia
        try:
            p = x.split(".")
            return f"{p[0]}.{p[1]}"
        except Exception:
            return x
    for a, t, b, via in sorted(relations):
        pdf.add_line(f"- {short(a)} {t} {short(b)} via '{via}'")

    # Escreve arquivo
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(pdf.build())


def write_dot(entities: Dict[str, Dict], relations: List[Tuple[str, str, str, str]], out_path: str):
    def node_name(full_label: str) -> str:
        app, model = full_label.split(".")
        return f"{app}_{model}"

    def esc(s: str) -> str:
        return s.replace("\n", " ").replace("\"", "\\\"").replace("|", "\\|").replace("{", "\\{").replace("}", "\\}")

    lines: List[str] = []
    lines.append("digraph ERD {")
    lines.append("  rankdir=LR;")
    lines.append("  node [shape=record, fontname=Helvetica];")
    lines.append("  edge [fontname=Helvetica, color=#555555];")

    # Nodes (compact: model name + até 12 campos)
    for full_label, ent in sorted(entities.items()):
        name = node_name(full_label)
        title = f"{ent['app']}.{ent['name']}"
        fields = []
        for fname, ftype, note in ent["fields"][:12]:
            suffix = f" ({note})" if note else ""
            fields.append(esc(f"{fname}: {ftype}{suffix}"))
        if len(ent["fields"]) > 12:
            fields.append("…")
        label = f"{{{esc(title)}|" + "\\l".join(fields) + "\\l}"
        lines.append(f"  \"{name}\" [label=\"{label}\"];")

    # Edges
    for a, t, b, via in sorted(relations):
        A = node_name(a)
        B = node_name(b)
        lbl = f"{t}\\n{via}"
        # Suaviza redundância visual: mesma cor para N:N
        color = "#2B8CBE" if t == "N:N" else "#6BAED6"
        lines.append(f"  \"{A}\" -> \"{B}\" [label=\"{esc(lbl)}\", color=\"{color}\"];")

    lines.append("}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_svg_simple(entities: Dict[str, Dict], relations: List[Tuple[str, str, str, str]], out_path: str):
    # Layout: colunas por app, caixas empilhadas; conectores curvas simples
    from collections import defaultdict

    # Config
    def _cfg():
        default_order = ['prefeituras','usuarios','cadastros','processos','denuncias','notificacoes','autoinfracao']
        app_order_env = os.environ.get('ERD_SVG_APP_ORDER')
        app_order = [a.strip() for a in app_order_env.split(',')] if app_order_env else default_order
        try:
            max_fields = int(os.environ.get('ERD_SVG_MAX_FIELDS', '8'))
        except Exception:
            max_fields = 8
        theme = {
            'bg_box': os.environ.get('ERD_SVG_COLOR_BG_BOX', '#ffffff'),
            'border_box': os.environ.get('ERD_SVG_COLOR_BORDER_BOX', '#CBD5E1'),
            'hdr_bg': os.environ.get('ERD_SVG_COLOR_HDR_BG', '#F8FAFC'),
            'hdr_border': os.environ.get('ERD_SVG_COLOR_HDR_BORDER', '#E2E8F0'),
            'text': os.environ.get('ERD_SVG_COLOR_TEXT', '#0F172A'),
            'muted': os.environ.get('ERD_SVG_COLOR_MUTED', '#475569'),
            'edge_n1': os.environ.get('ERD_SVG_COLOR_EDGE_N1', '#4F46E5'),
            'edge_nn': os.environ.get('ERD_SVG_COLOR_EDGE_NN', '#0EA5E9'),
        }
        return app_order, max_fields, theme

    app_order, max_fields, theme = _cfg()

    groups: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
    for lbl, ent in entities.items():
        groups[ent['app']].append((lbl, ent))
    for app in groups:
        groups[app].sort(key=lambda it: it[1]['name'])

    # Ordena colunas conforme preferência; apps não listadas vão ao final (ordem alfabética)
    ordered = [a for a in app_order if a in groups]
    others = [a for a in sorted(groups.keys()) if a not in app_order]
    apps = ordered + others
    if not apps:
        apps = sorted(groups.keys())
    col_w = 340
    col_gap = 72
    margin = 40
    title_h = 24
    line_h = 16

    # Measure heights and positions
    positions: Dict[str, Tuple[int,int,int,int,int]] = {}  # label -> (x,y,w,h,app_index)
    current_y_per_col: Dict[int, int] = {}

    for i, app in enumerate(apps):
        x = margin + i * (col_w + col_gap)
        y = margin
        current_y_per_col[i] = y
        for lbl, ent in groups[app]:
            fcount = min(len(ent['fields']), max_fields)
            h = title_h + fcount * line_h + 12
            positions[lbl] = (x, y, col_w, h, i)
            y += h + 24
        current_y_per_col[i] = y

    width = margin + len(apps) * (col_w + col_gap)
    height = max(current_y_per_col.values() or [margin]) + margin

    def esc(t: str) -> str:
        return (t or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Build SVG
    out: List[str] = []
    out.append(f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>")
    out.append(
        "<style> .t{font-family:Helvetica,Arial,sans-serif;font-size:12px;fill:%(text)s} "
        ".tt{font-weight:700} .box{fill:%(bg_box)s;stroke:%(border_box)s;stroke-width:1.2;rx:8} "
        ".hdr{fill:%(hdr_bg)s;stroke:%(hdr_border)s;stroke-width:1.2} "
        ".edge{stroke:%(edge_n1)s;stroke-width:1.2;fill:none} .edgeNN{stroke:%(edge_nn)s} "
        ".lbl{font-size:10px;fill:%(muted)s} </style>" % theme
    )
    out.append(
        "<defs>"
        f"<marker id='arrow' viewBox='0 0 10 10' refX='10' refY='5' markerWidth='6' markerHeight='6' orient='auto-start-reverse'><path d='M 0 0 L 10 5 L 0 10 z' fill='{theme['edge_n1']}'/></marker>"
        f"<marker id='arrowNN' viewBox='0 0 10 10' refX='10' refY='5' markerWidth='6' markerHeight='6' orient='auto-start-reverse'><path d='M 0 0 L 10 5 L 0 10 z' fill='{theme['edge_nn']}'/></marker>"
        "</defs>"
    )

    # App titles
    for i, app in enumerate(apps):
        x = margin + i * (col_w + col_gap)
        out.append(f"<text class='t tt' x='{x}' y='{margin-12}'>{esc(app)}</text>")

    # Draw boxes
    for lbl, ent in entities.items():
        x, y, w, h, _ = positions[lbl]
        out.append(f"<rect class='box' x='{x}' y='{y}' width='{w}' height='{h}' />")
        # header
        out.append(f"<rect class='hdr' x='{x}' y='{y}' width='{w}' height='{title_h+8}' />")
        title = f"{ent['app']}.{ent['name']}"
        out.append(f"<text class='t tt' x='{x+10}' y='{y+18}'>{esc(title)}</text>")
        # fields
        fy = y + title_h + 8 + 14
        for fname, ftype, note in ent['fields'][:max_fields]:
            suffix = f" ({note})" if note else ""
            out.append(f"<text class='t' x='{x+10}' y='{fy}'>{esc(fname)}: {esc(ftype)}{esc(suffix)}</text>")
            fy += line_h
        if len(ent['fields']) > max_fields:
            out.append(f"<text class='t' x='{x+10}' y='{fy}'>…</text>")

    # Edges
    def mid_line(x1,y1,x2,y2):
        return (x1 + x2)/2, (y1 + y2)/2

    for a, t, b, via in relations:
        x1, y1, w1, h1, i1 = positions.get(a, (0,0,0,0,0))
        x2, y2, w2, h2, i2 = positions.get(b, (0,0,0,0,0))
        if i1 <= i2:
            sx = x1 + w1
            sy = y1 + h1/2
            tx = x2
            ty = y2 + h2/2
        else:
            sx = x1
            sy = y1 + h1/2
            tx = x2 + w2
            ty = y2 + h2/2
        mx = (sx + tx)/2
        my = (sy + ty)/2
        cls = "edgeNN" if t == "N:N" else "edge"
        marker = "arrowNN" if t == "N:N" else "arrow"
        out.append(f"<path class='{cls}' d='M {sx} {sy} C {mx} {sy}, {mx} {ty}, {tx} {ty}' marker-end='url(#{marker})' />")
        out.append(f"<text class='lbl' x='{mx}' y='{my-4}' text-anchor='middle'>{esc(t)} {esc(via)}</text>")

    out.append("</svg>")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(out))


def main():
    setup_django()
    entities, relations = collect_models_info()
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    mermaid_path = os.path.join(docs_dir, "ERD.mmd")
    pdf_path = os.path.join(docs_dir, "erd.pdf")
    dot_path = os.path.join(docs_dir, "ERD.dot")
    svg_path = os.path.join(docs_dir, "ERD.svg")
    png_path = os.path.join(docs_dir, "ERD.png")
    write_mermaid(entities, relations, mermaid_path)
    write_pdf(entities, relations, pdf_path)
    # DOT + tentar renderizar com Graphviz se presente
    try:
        write_dot(entities, relations, dot_path)
        import shutil, subprocess
        if shutil.which("dot"):
            subprocess.run(["dot", "-Tsvg", dot_path, "-o", svg_path], check=True)
            subprocess.run(["dot", "-Tpng", dot_path, "-Gdpi=140", "-o", png_path], check=True)
            print(f"OK: {mermaid_path}, {pdf_path}, {dot_path}, {svg_path} e {png_path} gerados.")
        else:
            # Fallback: gerar SVG simples custom (sem Graphviz)
            simple_svg_path = svg_path
            write_svg_simple(entities, relations, simple_svg_path)
            print(f"OK: {mermaid_path}, {pdf_path}, {dot_path} e {simple_svg_path} gerados (fallback SVG simples sem Graphviz).")
    except Exception as e:
        print(f"OK (parcial): {mermaid_path} e {pdf_path}. Falha DOT/SVG: {e}")


if __name__ == "__main__":
    main()

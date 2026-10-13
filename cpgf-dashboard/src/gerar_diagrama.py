"""Gera docs/diagrama_pipeline.svg (e .png se o playwright estiver instalado)."""
from pathlib import Path
raiz = Path(__file__).resolve().parent.parent
INK, QUIET, EDGE, ACC, ACC_BG, BG = "#0b1f17", "#52625a", "#9fb0a7", "#0b5d3b", "#dcebe4", "#fcfcfb"
F = "font-family='Inter,Segoe UI,Helvetica,Arial,sans-serif'"

def box(x, y, w, h, main=False):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='10' fill='{ACC_BG if main else BG}' "
            f"stroke='{ACC if main else EDGE}' stroke-width='{2 if main else 1.25}'/>")

def badge(cx, cy, n, main=False):
    c = ACC if main else EDGE
    return (f"<circle cx='{cx}' cy='{cy}' r='12' fill='{ACC if main else BG}' stroke='{c}' stroke-width='1.25'/>"
            f"<text x='{cx}' y='{cy+4.5}' text-anchor='middle' font-size='12.5' font-weight='700' fill='{'#fff' if main else INK}' {F}>{n}</text>")

def txt(x, y, s, size=11.5, w=400, fill=QUIET):
    return f"<text x='{x}' y='{y}' font-size='{size}' font-weight='{w}' fill='{fill}' {F}>{s}</text>"

def arrow(d):
    return f"<path d='{d}' fill='none' stroke='{ACC}' stroke-width='1.5' marker-end='url(#a)'/>"

etapas = [
    (24, "Carga", ["CSV do portal (;)", "ISO-8859-1 e vírgula", "SQL stg · Python"], False),
    (208, "Tratamento", ["Tipos, datas e valor", "Flags de estorno", "e favorecido sigiloso"], False),
    (392, "Análises", ["Período e categoria", "Fornecedor (ABC)", "Faixa de valor"], False),
    (576, "Regras", ["6 regras com peso", "Contexto reduz score", "Validada em 766 casos"], True),
]
p = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 760 430' width='1520' height='860'>",
     f"<rect width='760' height='430' fill='{BG}'/>",
     f"<defs><marker id='a' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'><path d='M0 0L10 5L0 10z' fill='{ACC}'/></marker></defs>",
     txt(24, 34, "O contexto legítimo entra antes do alerta, não depois", 16, 700, INK),
     txt(24, 52, "Pipeline do projeto CPGF · 5 etapas, do CSV bruto à fila de investigação", 11.5, 400, QUIET),
     box(432, 66, 304, 56), txt(448, 88, "Contexto legítimo antes do alerta", 13, 600, INK),
     txt(448, 106, "fim de exercício · unidade 24h · evento anual"),
     arrow("M656 122V152"), arrow("M184 200H208"), arrow("M368 200H392"), arrow("M552 200H576"), arrow("M656 248V280")]
for x, nome, linhas, main in etapas:
    n = etapas.index((x, nome, linhas, main)) + 1
    p += [box(x, 152, 160, 96, main), badge(x + 22, 174, n, main), txt(x + 42, 179, nome, 13, 600, INK)]
    p += [txt(x + 16, 202 + 16 * i, l, 11.5, 400, INK if main else QUIET) for i, l in enumerate(linhas)]
p += [box(24, 280, 712, 128), badge(46, 300, 5), txt(66, 305, "Triagem e entrega", 13, 600, INK)]
saidas = [(40, "Fila de investigação", ["Ordenada por score e valor", "Hipóteses legítimas por alerta"]),
          (272, "Painel web", ["5 abas, filtros e tooltips", "Abre offline, sem servidor"]),
          (504, "Power BI e SQL", ["Modelo, DAX e 6 páginas", "4 scripts SQL Server"])]
for x, nome, linhas in saidas:
    p += [box(x, 322, 216, 72), txt(x + 16, 346, nome, 13, 600, INK)]
    p += [txt(x + 16, 364 + 16 * i, l) for i, l in enumerate(linhas)]
p.append("</svg>")
svg = raiz / "docs" / "diagrama_pipeline.svg"
svg.write_text("\n".join(p), encoding="utf-8")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1520, "height": 860})
        pg.goto(svg.as_uri()); pg.screenshot(path=str(raiz / "docs" / "diagrama_pipeline.png")); b.close()
    print("svg + png gerados")
except Exception as e:
    print("svg gerado (png ignorado):", e)

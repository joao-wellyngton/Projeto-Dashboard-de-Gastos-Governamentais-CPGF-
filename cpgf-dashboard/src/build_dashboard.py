"""Injeta out/dashboard_data.json no template e gera dashboard/index.html (arquivo único, abre offline)."""
from pathlib import Path
raiz = Path(__file__).resolve().parent.parent
dados = (raiz / "out" / "dashboard_data.json").read_text(encoding="utf-8").replace("</", "<\\/")
html = (raiz / "dashboard" / "template.html").read_text(encoding="utf-8").replace("/*__DATA__*/null", dados)
(raiz / "dashboard" / "index.html").write_text(html, encoding="utf-8")
print("dashboard/index.html gerado:", round(len(html) / 1e6, 2), "MB")

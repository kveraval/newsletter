#!/usr/bin/env python3
"""
Generador simplificado del newsletter usando Ollama Web Search.
Reemplazo temporal para cuando Tavily está agotado.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
NEWS_FILE = DATA_DIR / "news.json"
SEEN_FILE = DATA_DIR / "seen.json"
HTML_FILE = ROOT / "index.html"

TOPICS = [
    ("Innovación Bancaria Chile", "Chile banco innovación tecnología app digital 2026"),
    ("Open Banking", "Chile open banking open finance SFA interoperabilidad 2026"),
    ("IA en Banca", "Chile banca inteligencia artificial IA chatbot asistente 2026"),
    ("Fintech", "Chile fintech startup financiera regulación CMF 2026"),
    ("Tech Global", "fintech innovation AI banking digital payments news 2026"),
]

QUOTES = [
    '"La mejor manera de predecir el futuro es crearlo." — Peter Drucker',
    '"La innovación distingue al líder del seguidor." — Steve Jobs',
    '"El riesgo más grande es no tomar ninguno." — Mark Zuckerberg',
    '"Construye algo que importa."',
]


def run_ollama_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    cmd = ["ollama-search", query, str(max_results)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return []
        out = result.stdout
        parsed = []
        pattern = r'=+\nTítulo: (.+?)\nURL: (.+?)\n-+\n(.+?)(?=\n=+|$)'
        matches = re.findall(pattern, out, re.DOTALL)
        for title, url, content in matches:
            parsed.append({
                "title": title.strip(),
                "url": url.strip(),
                "content": content.strip()[:500],
                "score": 0.5,
            })
        return parsed
    except Exception as e:
        print(f"Error: {e}")
        return []


def run_ollama_extract(url: str) -> str:
    cmd = ["ollama-fetch", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return ""
        return result.stdout[:2000]  # Limitar contenido
    except Exception as e:
        print(f"Extract error: {e}")
        return ""


def seen_key(item: Dict[str, Any]) -> str:
    url = item.get("url", "").strip().lower()
    return url if url else item.get("title", "").strip().lower()[:50]


def is_relevant(title: str, content: str) -> bool:
    text = (title + " " + content).lower()
    bank_terms = [
        "banco", "banca", "bank", "fintech", "open banking", "banca abierta",
        "neobank", "tarjeta", "crédito", "digital bank", "pagos digitales",
        "inteligencia artificial", "AI", "machine learning", "chatbot",
        "blockchain", "cripto", "bitcoin", "regulación", "CMF",
    ]
    geo_terms = [
        "chile", "chilena", "chileno", "latam", "latin", "latinoamérica",
        "mexico", "brasil", "colombia", "argentina", "global", "mundo",
    ]
    return any(term in text for term in bank_terms) and any(term in text for term in geo_terms)


def normalize_source(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().replace("www.", "")
        return host
    except Exception:
        return url


def clean_summary(content: str) -> str:
    if not content:
        return ""
    # Limpiar basura
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) > 280:
        content = content[:280].rsplit(" ", 1)[0] + "…"
    return content


def classify_category(title: str, content: str) -> str:
    text = (title + " " + content).lower()
    if any(t in text for t in ["open banking", "open finance", "banca abierta", "sfa", "interoperabilidad"]):
        return "Open Banking Chile y Latam"
    if any(t in text for t in ["inteligencia artificial", "ia", "ai", "chatbot", "machine learning", "agente"]):
        return "Inteligencia Artificial en Banca Chile"
    if any(t in text for t in ["fintech", "startup", "neobanco", "cmf", "regulación"]):
        return "Fintech y Regulación"
    if "chile" in text:
        return "Innovación Bancaria y Productos Chile"
    return "Tecnología Financiera Global"


def collect_news() -> List[Dict[str, Any]]:
    all_results = []
    seen_urls = set()
    
    for category, query in TOPICS:
        print(f"Buscando: {category}...")
        results = run_ollama_search(query, max_results=3)
        
        for r in results:
            url = r.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            
            title = r.get("title", "Sin título")
            content = r.get("content", "")
            
            if not is_relevant(title, content):
                continue
            
            # Extraer contenido completo
            print(f"  Extrayendo: {title[:40]}...")
            full_content = run_ollama_extract(url)
            summary = clean_summary(full_content or content)
            
            all_results.append({
                "title": title,
                "url": url,
                "source": normalize_source(url),
                "summary": summary,
                "category": classify_category(title, content),
                "score": r.get("score", 0.5),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
        
        print(f"  Encontradas: {len([x for x in all_results if x.get('category') == category])}")
    
    # Ordenar por score y limitar a 10
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results[:10]


def build_html(news_items: List[Dict[str, Any]], quote: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_display = datetime.now(timezone.utc).strftime("%d de %B de %Y")
    
    # Agrupar por categoría
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for item in news_items:
        cat = item.get("category", "General")
        by_category.setdefault(cat, []).append(item)
    
    cards_html = ""
    for category in sorted(by_category.keys()):
        cards_html += f"""
    <div class="category">
      <h3>{category}</h3>
      {''.join(f'''
      <article class="card">
        <a class="title" href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a>
        <div class="meta">
          <span class="source">{item['source']}</span>
          <span class="dot"></span>
          <span>{item['date']}</span>
        </div>
        <p class="summary">{item.get('summary', '')}</p>
      </article>
      ''' for item in by_category[category])}
    </div>
    """
    
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>El Brief de Kay - {today}</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📰</text></svg>">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root {{ --bg: #ffffff; --surface: #f8fafc; --text: #1f2937; --text-muted: #475569; --text-light: #64748b; --accent: #2563eb; --accent-soft: #eff6ff; --border: #e2e8f0; --radius: 12px; --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06); }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: 'Inter', sans-serif; background: var(--surface); color: var(--text); line-height: 1.6; }}
    .container {{ max-width: 720px; margin: 0 auto; padding: 48px 24px 64px; }}
    header.top {{ text-align: center; padding-bottom: 32px; border-bottom: 1px solid var(--border); margin-bottom: 40px; }}
    header.top h1 {{ margin: 0; font-size: 2.4rem; font-weight: 700; letter-spacing: -0.02em; }}
    header.top .subtitle {{ margin: 12px 0 0; color: var(--text-muted); font-size: 1rem; }}
    header.top .quote {{ margin: 20px 0 0; font-style: italic; color: var(--text-muted); }}
    .category {{ margin-bottom: 36px; }}
    .category h3 {{ margin: 0 0 18px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent); padding: 6px 10px; background: var(--accent-soft); display: inline-block; border-radius: 6px; }}
    .card {{ background: var(--bg); border-radius: var(--radius); box-shadow: var(--shadow); padding: 22px 24px; margin-bottom: 16px; border: 1px solid var(--border); transition: transform 0.15s ease; }}
    .card:hover {{ transform: translateY(-2px); }}
    .card a.title {{ display: block; text-decoration: none; color: var(--text); font-size: 1.15rem; font-weight: 600; margin-bottom: 10px; line-height: 1.35; }}
    .card a.title:hover {{ color: var(--accent); }}
    .meta {{ display: flex; gap: 8px; align-items: center; font-size: 0.78rem; color: var(--text-light); margin-bottom: 10px; }}
    .meta .source {{ font-weight: 600; color: var(--text-muted); }}
    .summary {{ font-size: 0.95rem; color: var(--text); margin: 0; }}
    footer {{ text-align: center; padding: 48px 0 24px; color: var(--text-light); font-size: 0.8rem; border-top: 1px solid var(--border); }}
    @media (max-width: 560px) {{ .container {{ padding: 32px 18px 48px; }} header.top h1 {{ font-size: 2rem; }} .card {{ padding: 18px 20px; }} }}
  </style>
</head>
<body>
  <div class="container">
    <header class="top">
      <h1>📰 El Brief de Kay</h1>
      <p class="subtitle">Open banking, IA, innovación bancaria y productos financieros en Chile y Latam.</p>
      <p class="quote">{quote}</p>
    </header>
    <main>
      {cards_html if cards_html else '<p style="text-align:center;color:var(--text-muted);padding:48px 0;">No se encontraron noticias hoy.</p>'}
    </main>
    <footer>
      Generado automáticamente · {datetime.now(timezone.utc).year} · <a href="https://github.com/draco-agent/tech-news-digest">Powered by OpenClaw</a>
    </footer>
  </div>
</body>
</html>"""


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Generando newsletter para {today}...")
    
    # Buscar noticias
    print("\n🔍 Buscando noticias con Ollama...")
    news = collect_news()
    
    if not news:
        print("⚠️ No se encontraron noticias")
        return
    
    print(f"\n✅ Total noticias: {len(news)}")
    
    # Seleccionar quote
    quote = QUOTES[datetime.now(timezone.utc).day % len(QUOTES)]
    
    # Generar HTML
    html = build_html(news, quote)
    HTML_FILE.write_text(html, encoding="utf-8")
    
    # Guardar historial
    history = []
    if NEWS_FILE.exists():
        history = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    
    # Agregar solo noticias nuevas
    seen = set()
    for item in history:
        seen.add(item.get("url", ""))
    
    for item in news:
        if item.get("url") not in seen:
            history.append(item)
            seen.add(item["url"])
    
    NEWS_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    SEEN_FILE.write_text(json.dumps(list(seen), indent=2), encoding="utf-8")
    
    print(f"\n✅ HTML generado: {HTML_FILE}")
    print(f"✅ Noticias guardadas: {NEWS_FILE}")
    print(f"📊 Total histórico: {len(history)}")
    
    # Mostrar resumen
    print("\n📰 Noticias de hoy:")
    for i, item in enumerate(news, 1):
        print(f"  {i}. {item['title'][:60]}... ({item['category']})")


if __name__ == "__main__":
    main()

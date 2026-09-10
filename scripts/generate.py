#!/usr/bin/env python3
"""
Generador de newsletter diaria de noticias tecnológicas/bancarias.
Busca con Tavily, filtra duplicados, actualiza news.json e index.html.
"""
import json
import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEEN_FILE = DATA_DIR / "seen.json"
NEWS_FILE = DATA_DIR / "news.json"
HTML_FILE = ROOT / "index.html"

TOPICS = [
    {
        "category": "Innovación Bancaria y Productos Chile",
        "queries": [
            "banca digital Chile noticias hoy",
            "innovación bancaria Chile noticias hoy",
            "Banco de Chile productos digitales noticias",
            "BancoEstado Chile productos digitales noticias",
            "Banco Itaú Chile innovación noticias",
            "Santander Chile banca digital noticias",
            "BCI Chile banca digital noticias",
            "Scotiabank Chile productos digitales noticias",
            "Tenpo Chile fintech noticias",
            "Bice Chile banca digital noticias",
            "Fintoc Chile open banking noticias",
            "fintech Chile noticias hoy",
        ],
    },
    {
        "category": "Open Banking Chile y Latam",
        "queries": [
            "open banking Chile noticias hoy",
            "banca abierta Chile CMF noticias",
            "open finance Chile noticias",
            "open banking Latam noticias",
            "open finance Brasil noticias hoy",
            "open banking México noticias hoy",
        ],
    },
    {
        "category": "Inteligencia Artificial en Banca Chile",
        "queries": [
            "IA inteligencia artificial banca Chile noticias",
            "bancos chilenos IA inteligencia artificial noticias",
            "Banco de Chile IA inteligencia artificial",
            "BancoEstado IA inteligencia artificial",
            "Itaú Chile IA inteligencia artificial",
            "BCI Chile IA inteligencia artificial",
            "Santander Chile IA noticias",
            "AI banking Latin America news",
        ],
    },
    {
        "category": "Tecnología Financiera Global",
        "queries": [
            "fintech innovation news today",
            "digital banking technology news",
        ],
    },
]

BLOCKED_DOMAINS = {
    "facebook.com", "fb.watch", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be", "tiktok.com", "reddit.com", "pinterest.com",
    "espn.com", "imdb.com", "spotify.com", "apple.com", "bitget.com",
    "beinsure.com", "ffnews.com", "kchcomunicacion.com", "fundssociety.com",
    "xtb.com", "ecosistemastartup.com", "bebee.com", "rosariofinanzas.ar",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:80]


def seen_key(item: Dict[str, Any]) -> str:
    url = item.get("url", "").strip().lower()
    title = item.get("title", "").strip().lower()
    if url:
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    return hashlib.sha256(title.encode()).hexdigest()[:16]


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    cmd = [
        "/root/.tavily-env/bin/tvly",
        "search",
        query,
        "--max-results",
        str(max_results),
        "--time-range",
        "day",
        "--topic",
        "news",
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            print(f"Tavily error ({query}): {result.stderr[:200]}")
            return []
        parsed = json.loads(result.stdout)
        return parsed.get("results", [])
    except Exception as e:
        print(f"Exception querying Tavily ({query}): {e}")
        return []


def normalize_source(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        host = host.replace("www.", "")
        if host.startswith("m."):
            host = host[2:]
        return host
    except Exception:
        return url


def clean_summary(content: str) -> str:
    if not content:
        return ""
    # Drop country-code selectors and obvious artifacts
    content = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*\+\d{1,4}\b", "", content)
    content = re.sub(r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", "", content)
    content = re.sub(r"#+", "", content)
    content = re.sub(r"\*+", "", content)
    content = re.sub(r"\[\.\.\.\]", "", content)
    # Strip leading stray punctuation and fragments
    content = re.sub(r"^[\.\,\;\:\-\|\s]+", "", content)
    # Strip common website menu crumbs and emojis with following category text
    content = re.sub(r"[👥🔍💼📊✅].{0,80}(?:\:|$)", "", content, flags=re.UNICODE)
    menu_words = [
        "Respuestas", "que Hora", "Loterias", "Tramites", "Empleos", "Deportes",
        "Farándula", "Virales", "Horóscopo", "Efemérides", "Trends", "Streamers",
        "TikTok", "YouTube", "Kick", "IRL", "Cual", "Cuanto", "Colombia", "Venezuela",
        "Argentina", "Mexico", "Espana", "Usa", "Estados Unidos", "carreras", "Actualidad",
        "Venture Capital", "Inversiones", "Rondas, fondos", "IA Tecnología", "Web3",
        "Modelos de Negocio", "Propósito", "Erradicar", "Construir en la comunidad",
        "Lo Último", "Lo Mas Leido", "Lo Más Leído", "Banco de Chile B Startup",
        "Menú", "Ir al contenido", "Inicio", "Noticias", "Más noticias", "Postulantes",
        "Estudiantes", "Académicas/os", "Funcionarias/os", "Egresadas/os",
        "Notas relacionadas", "Negocios", "Destacados", "Aerolíneas", "SERNAC",
        "Icare", "Informe de Política Monetaria", "Rosanna Costa",
    ]
    for word in menu_words:
        content = re.sub(r"\b" + re.escape(word) + r"\b[^.]*", "", content, flags=re.IGNORECASE)
    # Remove isolated short fragments separated by dots that look like menus
    content = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\s*:\s*", "", content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


def extract_summary(content: str, max_len: int = 240) -> str:
    content = clean_summary(content)
    if not content:
        return ""
    if len(content) <= max_len:
        return content
    return content[:max_len].rsplit(" ", 1)[0] + "…"


def is_relevant(title: str, content: str) -> bool:
    text = (title + " " + content).lower()
    bank_terms = [
        "banco", "banca", "bank", "bancario", "bancaria", "fintech", "open banking",
        "open finance", "banca abierta", "neobank", "neobanco", "core banking",
        "tarjeta", "crédito", "credito", "ahorro", "cuenta bancaria", "digital bank",
        "pagos digitales", "plataforma financiera", "servicios financieros",
        "lending", "préstamo", "prestamo", "hipotec", "producto bancario",
        "bancoestado", "banco de chile", "itaú", "itau", "santander", "bice",
        "scotiabank", "falabella", "cmr", "tenpo", "mercado pago", "nubank",
        "inteligencia artificial", "artificial intelligence", "machine learning",
        "modelo de ia", "ia en", "ai en", "agentes de ia", "fraudes", "detección",
    ]
    geo_terms = [
        "chile", "chilena", "chileno", "latam", "latin", "latinoamérica", "latinoamerica",
        "mexico", "méxico", "brasil", "brazil", "colombia", "argentina",
        "perú", "peru", "ecuador", "uruguay", "paraguay", "bolivia",
    ]
    has_bank = any(term in text for term in bank_terms)
    has_geo = any(term in text for term in geo_terms)
    return has_bank and has_geo


def score_chile_priority(item: Dict[str, Any]) -> float:
    """Boost score for items explicitly about Chile."""
    title = item.get("title", "").lower()
    content = (item.get("content", "") or "").lower()
    base = item.get("score", 0.0)
    chile_markers = ["chile", "chilena", "chileno", "chilenos", "chilenas", "santiago"]
    bank_markers = ["banco", "banca", "bancoestado", "banco de chile", "itaú", "itau", "santander", "bice", "scotiabank", "tenpo", "falabella", "cmr"]
    boost = 0.0
    if any(m in title for m in chile_markers):
        boost += 0.15
    if any(m in content for m in chile_markers):
        boost += 0.05
    if any(m in title for m in bank_markers):
        boost += 0.05
    return base + boost


def is_chilean_source(url: str) -> bool:
    """Detect if URL domain suggests a Chilean news source."""
    host = normalize_source(url)
    chile_tlds = [".cl"]
    chile_domains = [
        "df.cl", "elmostrador.cl", "theclinic.cl", "chocale.cl", "trendtic.cl",
        "fintoc.com", "tenpo.cl", "bci.cl", "bancoestado.cl", "bancochile.cl",
        "itauchile.cl", "santander.cl", "scotiabankcl.com", "bice.cl",
        "fch.cl", "uchile.cl", "brinca.com", "auroranoticias.cl",
    ]
    return any(host.endswith(tld) for tld in chile_tlds) or any(host == d or host.endswith("." + d) for d in chile_domains)


def classify_category(title: str, content: str, url: str = "") -> str:
    """Classify by explicit topic signals. Fallback to global fintech."""
    text = (title + " " + content).lower()
    title_lower = title.lower()
    open_terms = ["open banking", "open finance", "banca abierta", "open data", "apis abiertas", "open insurance"]
    ai_title_terms = [
        "inteligencia artificial", "artificial intelligence", "machine learning",
        "modelo de ia", "ia en banca", "ai en banca", "agentes de ia", "banca con ia",
    ]
    chile_markers = ["chile", "chilena", "chileno", "chilenos", "chilenas", "santiago"]
    is_chile_term = any(m in text for m in chile_markers)
    is_chilean = is_chile_term and is_chilean_source(url)
    is_open = any(t in title_lower for t in open_terms) or any(t in text for t in open_terms)
    is_ai = any(t in title_lower for t in ai_title_terms) and \
            any(t in text for t in ["banco", "banca", "bank", "fintech", "financier", "crédito", "tarjeta", "pagos", "digital bank"])
    is_econ_policy = any(t in text for t in [
        "banco central", "banco central de chile", "política monetaria", "inflación",
        "tasas", "cop", "hacienda",
        "crecimiento económico", "ipom", "pib", "economía chilena", "rosanna costa",
    ]) and not any(t in title_lower for t in ["ley fintech", "fintech", "producto bancario", "tarjeta", "cuenta", "banca digital"])
    is_chile_bank = is_chile_term and \
                    any(t in text for t in ["banco", "banca", "fintech", "producto", "tarjeta", "crédito", "cuenta", "bancoestado", "banco de chile", "itaú", "itau", "santander", "bice", "scotiabank", "tenpo", "falabella", "cmr"])
    is_chile_tech = is_chile_term and any(t in text for t in ["inteligencia artificial", "artificial intelligence", "machine learning", "ia", "tecnología", "digital", "innovación tecnológica"])

    if is_open:
        return "Open Banking Chile y Latam"
    if is_ai:
        return "Inteligencia Artificial en Banca Chile"
    if is_econ_policy and is_chile_term:
        return "Economía y Política Monetaria Chile"
    if is_chile_bank:
        return "Innovación Bancaria y Productos Chile"
    if is_chilean and is_chile_tech:
        return "IA y Tecnología Chile"
    if is_chile_term:
        return "Innovación Bancaria y Productos Chile"
    return "Tecnología Financiera Global"


def is_quality_summary(summary: str, title: str) -> bool:
    """Reject summaries that look like site menus, concatenated headlines, or punctuation soup."""
    if not summary or len(summary) < 20:
        return False
    lower = summary.lower()
    # Require a reasonable ratio of real words to total characters
    real_words = re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}", summary)
    if len(real_words) < 6:
        return False
    alpha_ratio = sum(len(w) for w in real_words) / max(len(summary), 1)
    if alpha_ratio < 0.35:
        return False
    menu_words = [
        "suscríbete", "newsletter", "internacional", "español", "português", "english",
        "menú", "home", "noticias:", "mercados", "pensiones", "negocio", "alternativos",
        "empleos", "deportes", "farándula", "virales", "horóscopo", "trends", "streamers",
        "carreras", "actualidad", "lo último", "lo mas leido", "lo más leído", "site docs",
        "venture capital", "ia  tecnología", "modelos de negocio", "propósito:",
        "ia & tecnología", "ia and tecnología", "tendencias,", "notas relacionadas",
        "ir al contenido", "postulantes", "estudiantes", "académicas/os", "funcionarias/os",
        "egresadas/os", "más noticias", "destacados", "sernac", "aerolíneas",
        "icare", "informe de política monetaria", "rosanna costa", "banco central de chile",
    ]
    menu_count = sum(1 for w in menu_words if w in lower)
    if menu_count >= 2:
        return False
    capitalized_phrases = len(re.findall(r"[A-Z][A-Za-z0-9]{2,}(?:\s+[A-Z][A-Za-z0-9]{2,}){2,}", summary))
    if capitalized_phrases >= 4:
        return False
    return True


def dedupe_and_merge(all_items: List[Dict[str, Any]], seen: set) -> List[Dict[str, Any]]:
    new_items = []
    min_score = 0.20
    kept_titles: List[str] = []
    for item in all_items:
        key = seen_key(item)
        if key in seen:
            continue
        title = item.get("title", "").strip()
        content = item.get("content", "") or ""
        url = item.get("url", "").strip()
        score = item.get("score", 0.0)
        if not title or not url or score < min_score:
            continue
        if is_pdf_url(url):
            continue
        if not is_relevant(title, content):
            continue
        source = normalize_source(url)
        if source in BLOCKED_DOMAINS:
            continue
        if any(b in source for b in ["porn", "xxx", "bet", "casino", "viagra", "onlyfans"]):
            continue
        summary = extract_summary(content)
        if not is_quality_summary(summary, title):
            continue
        # Skip if topic is nearly identical to one already kept
        if any(is_duplicate_topic(title, kt) for kt in kept_titles):
            continue
        kept_titles.append(title)
        seen.add(key)
        new_items.append(
            {
                "id": key,
                "title": title,
                "url": url,
                "source": source,
                "summary": summary,
                "published": item.get("published_date", ""),
                "score": score,
            }
        )
    return new_items


def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf") or "/site/docs/" in url.lower()


def is_duplicate_topic(title1: str, title2: str) -> bool:
    """Detect near-duplicate stories by shared significant words."""
    stop = {"de", "la", "el", "en", "y", "a", "que", "con", "por", "para", "del", "al", "los", "las", "un", "una", "su", "se", "es", "son", "al", "más", "mas", "noticia", "ee", "uu", "eeuu", "us", "news"}
    words1 = set(w for w in re.sub(r"[^\w]", " ", title1.lower()).split() if len(w) > 2 and w not in stop)
    words2 = set(w for w in re.sub(r"[^\w]", " ", title2.lower()).split() if len(w) > 2 and w not in stop)
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2)
    return overlap >= 3 and overlap / min(len(words1), len(words2)) >= 0.5


def collect_news() -> List[Dict[str, Any]]:
    all_results = []
    for topic in TOPICS:
        for query in topic["queries"]:
            print(f"Buscando: {query}")
            results = run_tavily(query, max_results=6)
            for r in results:
                r["_category"] = topic["category"]
            all_results.extend(results)
    # Sort by relevance score descending before dedup to keep best first
    all_results.sort(key=lambda x: score_chile_priority(x), reverse=True)
    # Deduplicate by URL and title similarity
    seen_urls: set = set()
    seen_titles: set = set()
    deduped_results = []
    for r in all_results:
        url = r.get("url", "").strip().lower()
        title_norm = re.sub(r"[^\w]", "", r.get("title", "").lower())
        if url in seen_urls:
            continue
        duplicate_title = False
        for existing in seen_titles:
            if existing and (existing in title_norm or title_norm in existing) and len(existing) > 20:
                duplicate_title = True
                break
        if duplicate_title:
            continue
        if url:
            seen_urls.add(url)
        if title_norm:
            seen_titles.add(title_norm)
        deduped_results.append(r)
    # Deduplicate globally and filter
    seen: set = set()
    merged = dedupe_and_merge(deduped_results, seen)
    # Classify by content
    for m in merged:
        m["category"] = classify_category(m["title"], m["summary"], m["url"])
    return merged


def select_items_chile_priority(items: List[Dict[str, Any]], total_limit: int = 10, max_global: int = 3) -> List[Dict[str, Any]]:
    """Pick items ensuring Chile-related news dominates the edition."""
    chile_items = []
    global_items = []
    for item in items:
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        if "chile" in text or "chilena" in text or "chileno" in text or "santiago" in text:
            chile_items.append(item)
        else:
            global_items.append(item)

    selected = []
    # Take all Chile items first, up to the total limit
    selected.extend(chile_items[:total_limit])
    # Fill remainder with global items, up to max_global
    remaining = total_limit - len(selected)
    if remaining > 0:
        selected.extend(global_items[:min(remaining, max_global)])
    return selected


def build_html(news_by_date: Dict[str, List[Dict[str, Any]]], title: str = "Newsletter Financiera") -> str:
    css = """
:root {
  --bg: #f6f7f9;
  --card: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --accent: #0f766e;
  --accent-light: #ccfbf1;
  --border: #e5e7eb;
  --radius: 14px;
  --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.05);
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.55;
}
.container {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 20px 60px;
}
header {
  text-align: center;
  padding: 28px 0 36px;
}
header h1 {
  margin: 0;
  font-size: 2.2rem;
  letter-spacing: -0.5px;
  color: var(--text);
}
header p {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 1.05rem;
}
.badge {
  display: inline-block;
  background: var(--accent);
  color: white;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 5px 10px;
  border-radius: 999px;
  margin-bottom: 14px;
}
.date-section {
  margin-bottom: 42px;
}
.date-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0 0 18px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--border);
}
.date-header h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
}
.date-header .count {
  color: var(--muted);
  font-size: 0.9rem;
}
.category {
  margin-bottom: 22px;
}
.category h3 {
  margin: 0 0 12px;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
}
.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 20px;
  margin-bottom: 14px;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.card:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.08);
}
.card a.title {
  display: block;
  text-decoration: none;
  color: var(--text);
  font-size: 1.05rem;
  font-weight: 700;
  margin-bottom: 6px;
  line-height: 1.35;
}
.card a.title:hover {
  color: var(--accent);
}
.meta {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 8px;
}
.meta .source {
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-light);
  padding: 2px 8px;
  border-radius: 6px;
}
.summary {
  font-size: 0.95rem;
  color: var(--text);
  margin: 0;
}
footer {
  text-align: center;
  padding: 40px 0 20px;
  color: var(--muted);
  font-size: 0.85rem;
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 40px 0;
}
@media (max-width: 520px) {
  header h1 { font-size: 1.7rem; }
  .container { padding: 20px 14px 40px; }
}
""".strip()

    def card_html(item: Dict[str, Any]) -> str:
        return f"""
        <article class="card">
          <a class="title" href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a>
          <div class="meta">
            <span class="source">{item['source']}</span>
            <span>{item.get('published', '')}</span>
          </div>
          <p class="summary">{item.get('summary', '')}</p>
        </article>
        """

    sections = []
    for date in sorted(news_by_date.keys(), reverse=True):
        items = news_by_date[date]
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(item.get("category", "General"), []).append(item)
        categories_html = ""
        for category in sorted(grouped.keys()):
            categories_html += f"""
            <div class="category">
              <h3>{category}</h3>
              {"".join(card_html(i) for i in grouped[category])}
            </div>
            """
        sections.append(f"""
        <section class="date-section">
          <div class="date-header">
            <h2>{date}</h2>
            <span class="count">{len(items)} noticia{'s' if len(items) != 1 else ''}</span>
          </div>
          {categories_html}
        </section>
        """)

    body = "".join(sections) if sections else "<p class='empty'>Aún no hay noticias para mostrar.</p>"

    return f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
  <div class="container">
    <header>
      <span class="badge">Daily Brief</span>
      <h1>{title}</h1>
      <p>Open banking, IA, innovación bancaria y productos financieros en Chile y Latam.</p>
    </header>
    <main>
      {body}
    </main>
    <footer>
      Generado automáticamente · Actualizado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </footer>
  </div>
</body>
</html>
"""


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen = set(load_json(SEEN_FILE, []))
    news_history = load_json(NEWS_FILE, [])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Fecha edición: {today}")

    new_items = collect_news()
    # Prioritize Chilean news and limit total edition size
    new_items = select_items_chile_priority(new_items, total_limit=10, max_global=3)

    # Add date and limit items per category per day
    per_category_limit = 6
    category_counts: Dict[str, int] = {}
    limited_items = []
    for item in new_items:
        cat = item.get("category", "General")
        if category_counts.get(cat, 0) >= per_category_limit:
            continue
        category_counts[cat] = category_counts.get(cat, 0) + 1
        item["date"] = today
        limited_items.append(item)
    new_items = limited_items

    # Merge into history
    for item in new_items:
        news_history.append(item)
        seen.add(item["id"])

    # Rebuild history keeping only the first occurrence of each URL
    unique_history: Dict[str, Dict[str, Any]] = {}
    for item in news_history:
        key = item.get("id") or seen_key(item)
        if key not in unique_history:
            unique_history[key] = item
    news_history = list(unique_history.values())

    # Group by date descending
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for item in news_history:
        by_date.setdefault(item["date"], []).append(item)

    HTML_FILE.write_text(build_html(by_date), encoding="utf-8")
    save_json(SEEN_FILE, sorted(seen))
    save_json(NEWS_FILE, news_history)
    print(f"Generadas {len(new_items)} noticias nuevas. Total histórico único: {len(news_history)}")
    print(f"HTML escrito: {HTML_FILE}")


if __name__ == "__main__":
    main()

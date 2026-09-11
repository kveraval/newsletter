#!/usr/bin/env python3
"""
Generador de newsletter diaria de noticias tecnológicas/bancarias.
Busca con Tavily, filtra duplicados, extrae contenido limpio e imágenes,
y actualiza news.json e index.html.
"""
import json
import hashlib
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEEN_FILE = DATA_DIR / "seen.json"
NEWS_FILE = DATA_DIR / "news.json"
HTML_FILE = ROOT / "index.html"

DAILY_QUOTES = [
    '"La mejor manera de predecir el futuro es crearlo." — Peter Drucker',
    '"La innovación distingue al líder del seguidor." — Steve Jobs',
    '"No busques errores, busca soluciones." — Henry Ford',
    '"El riesgo más grande es no tomar ninguno." — Mark Zuckerberg',
    '"La transformación digital no es opcional, es inevitable."',
    '"Cada crisis es una oportunidad disfrazada." — Albert Einstein',
    '"Quien no se mueve no siente sus cadenas." — Rosa Luxemburgo',
    '"El dinero no es el objetivo. La libertad sí."',
    '"Los datos son el nuevo petróleo, pero la intuición sigue siendo el motor."',
    '"Construye algo que importe."',
]

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
    "cl.trabajo.org", "adnradio.cl", "araucanianoticias.cl", "tabulado.net",
    "paislobo.cl", "chocale.cl",
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


def normalize_title(title: str) -> str:
    """Convert ALL CAPS titles to title case."""
    if title.isupper():
        return title.title()
    return title


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


def extract_article(url: str) -> Dict[str, Any]:
    """Extract clean article content and images with Tavily extract."""
    cmd = [
        "/root/.tavily-env/bin/tvly",
        "extract",
        url,
        "--include-images",
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {}
        parsed = json.loads(result.stdout)
        results = parsed.get("results", []) if parsed else []
        if not results:
            return {}
        first = results[0]
        return {
            "content": first.get("raw_content", "") or first.get("content", "") or first.get("text", ""),
            "images": first.get("images", []) or [],
        }
    except Exception as e:
        print(f"Extract error ({url}): {e}")
        return {}


def first_substantial_paragraph(text: str, min_len: int = 80, max_len: int = 260) -> str:
    """Pick the first paragraph that looks like real article content."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for p in paragraphs:
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) < min_len:
            continue
        lower = p.lower()
        if any(w in lower for w in ["menú", "home", "noticias:", "suscríbete", "compartir", "ir al contenido"]):
            continue
        if len(p) > max_len:
            p = p[:max_len].rsplit(" ", 1)[0] + "…"
        return p
    return ""


def summarize_with_ollama(text: str, model: str = "llama3.2:latest", max_input: int = 1800) -> str:
    """Summarize article text using local Ollama HTTP API."""
    text = text.strip()
    if not text:
        return ""
    if len(text) > max_input:
        text = text[:max_input].rsplit(" ", 1)[0]
    prompt = (
        "Eres un editor de una newsletter financiera. Resume el siguiente artículo en español en máximo 2 oraciones cortas. "
        "Usa solo información relevante del sector financiero, bancario, fintech o tecnológico en Chile o Latinoamérica. "
        "No repitas el título. No incluyas menús, publicidad, fechas de publicación ni texto repetido. "
        "Responde únicamente con el resumen, sin introducción.\n\n"
        f"{text}\n\nResumen:"
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 200},
    }
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        summary = result.get("response", "").strip()
        summary = re.sub(r"^(Resumen:|Aquí tienes el resumen:?\s*|El resumen es:?\s*)", "", summary, flags=re.IGNORECASE).strip()
        summary = re.sub(r'"', "", summary)
        if len(summary) > 300:
            summary = summary[:300].rsplit(" ", 1)[0] + "…"
        return summary
    except Exception as e:
        print(f"Ollama API exception: {e}")
        return ""


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
    content = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*\+\d{1,4}\b", "", content)
    content = re.sub(r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", "", content)
    content = re.sub(r"#+", "", content)
    content = re.sub(r"\*+", "", content)
    content = re.sub(r"\[\.\.\.\]", "", content)
    content = re.sub(r"^[\.\,\;\:\-\|\s]+", "", content)
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
    host = normalize_source(url)
    chile_tlds = [".cl"]
    chile_domains = [
        "df.cl", "elmostrador.cl", "theclinic.cl", "trendtic.cl",
        "fintoc.com", "tenpo.cl", "bci.cl", "bancoestado.cl", "bancochile.cl",
        "itauchile.cl", "santander.cl", "scotiabankcl.com", "bice.cl",
        "fch.cl", "uchile.cl", "brinca.com", "auroranoticias.cl",
    ]
    return any(host.endswith(tld) for tld in chile_tlds) or any(host == d or host.endswith("." + d) for d in chile_domains)


def classify_category(title: str, content: str, url: str = "") -> str:
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
    if not summary or len(summary) < 20:
        return False
    lower = summary.lower()
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


def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf") or "/site/docs/" in url.lower()


def is_duplicate_topic(title1: str, title2: str) -> bool:
    stop = {"de", "la", "el", "en", "y", "a", "que", "con", "por", "para", "del", "al", "los", "las", "un", "una", "su", "se", "es", "son", "al", "más", "mas", "noticia", "ee", "uu", "eeuu", "us", "news"}
    words1 = set(w for w in re.sub(r"[^\w]", " ", title1.lower()).split() if len(w) > 2 and w not in stop)
    words2 = set(w for w in re.sub(r"[^\w]", " ", title2.lower()).split() if len(w) > 2 and w not in stop)
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2)
    return overlap >= 3 and overlap / min(len(words1), len(words2)) >= 0.5


def dedupe_and_merge(all_items: List[Dict[str, Any]], seen: set) -> List[Dict[str, Any]]:
    new_items = []
    min_score = 0.20
    kept_titles: List[str] = []
    for item in all_items:
        key = seen_key(item)
        if key in seen:
            continue
        title = normalize_title(item.get("title", "").strip())
        content = item.get("content", "") or ""
        url = item.get("url", "").strip()
        score = item.get("score", 0.0)
        if not title or not url or score < min_score:
            continue
        if is_pdf_url(url):
            continue
        if not is_relevant(title, content):
            continue
        # Skip job postings and generic lifestyle content
        combined = (title + " " + content).lower()
        if any(t in combined for t in ["oferta de trabajo", "empleo", "careers", "jobs", "trabajo.org", "cómo obtener", "beneficio del minvu", "vivienda"]):
            continue
        source = normalize_source(url)
        if source in BLOCKED_DOMAINS:
            continue
        if any(b in source for b in ["porn", "xxx", "bet", "casino", "viagra", "onlyfans"]):
            continue
        summary = extract_summary(content)
        if not is_quality_summary(summary, title):
            continue
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
                "image": item.get("image", "") or "",
            }
        )
    return new_items


def pick_best_image(images: List[str]) -> str:
    """Pick the largest-looking image, skipping logos, icons, avatars and small thumbnails."""
    skip_patterns = ["gravatar", "logo", "icon", "favicon", "150x150", "187x62", "300x146", "300x147", "300x148", "300x134", "62x", "avatar"]
    for img in images:
        lower = img.lower()
        if any(p in lower for p in skip_patterns):
            continue
        return img
    return ""


def enrich_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract clean content and image for a news item, and summarize with Ollama."""
    extracted = extract_article(item["url"])
    if not extracted:
        return item
    images = extracted.get("images", []) or []
    if images and not item.get("image"):
        best = pick_best_image(images)
        if best:
            item["image"] = best
    raw_text = extracted.get("content", "") or ""
    if raw_text:
        clean = first_substantial_paragraph(raw_text)
        if clean:
            item["summary"] = clean
        ai_summary = summarize_with_ollama(raw_text)
        if ai_summary and len(ai_summary) > 40:
            item["summary"] = ai_summary
    return item


def collect_news() -> List[Dict[str, Any]]:
    all_results = []
    for topic in TOPICS:
        for query in topic["queries"]:
            print(f"Buscando: {query}")
            results = run_tavily(query, max_results=6)
            for r in results:
                r["_category"] = topic["category"]
            all_results.extend(results)
    all_results.sort(key=lambda x: score_chile_priority(x), reverse=True)
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
    seen: set = set()
    merged = dedupe_and_merge(deduped_results, seen)
    for m in merged:
        m["category"] = classify_category(m["title"], m["summary"], m["url"])

    # Enrich top items with clean extraction and AI summaries (limit to avoid long runs)
    for item in merged[:8]:
        try:
            enrich_item(item)
        except Exception as e:
            print(f"Enrichment failed for {item.get('url', '')}: {e}")

    return merged


def select_items_chile_priority(items: List[Dict[str, Any]], total_limit: int = 10, max_global: int = 3) -> List[Dict[str, Any]]:
    chile_items = []
    global_items = []
    for item in items:
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        if "chile" in text or "chilena" in text or "chileno" in text or "santiago" in text:
            chile_items.append(item)
        else:
            global_items.append(item)

    selected = []
    selected.extend(chile_items[:total_limit])
    remaining = total_limit - len(selected)
    if remaining > 0:
        selected.extend(global_items[:min(remaining, max_global)])
    return selected


def format_date_header(date_str: str) -> str:
    """Format YYYY-MM-DD to a human-readable Spanish date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{weekdays[dt.weekday()]} {dt.day} de {months[dt.month - 1]} de {dt.year}"
    except Exception:
        return date_str


def format_relative_badge(published_str: str, section_date: str) -> str:
    """Return a small human-readable badge for how recent an article is."""
    if not published_str:
        return ""
    try:
        pub_dt = parsedate_to_datetime(published_str)
        section_dt = datetime.strptime(section_date, "%Y-%m-%d")
        delta_days = (section_dt.date() - pub_dt.date()).days
        if delta_days == 0:
            return "hoy"
        elif delta_days == 1:
            return "ayer"
        elif delta_days < 7:
            return f"hace {delta_days} días"
        return ""
    except Exception:
        return ""


def format_card_date(published_str: str) -> str:
    """Return a short readable date from an RSS/HTTP date string."""
    if not published_str:
        return ""
    try:
        dt = parsedate_to_datetime(published_str)
        return dt.strftime("%d/%m/%Y · %H:%M")
    except Exception:
        return published_str


def build_html(news_by_date: Dict[str, List[Dict[str, Any]]], title: str = "El Brief de Kay", daily_quote: str = "") -> str:
    css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');

:root {
  --bg: #ffffff;
  --surface: #f8fafc;
  --card: #ffffff;
  --text: #1f2937;
  --text-muted: #475569;
  --text-light: #64748b;
  --accent: #2563eb;
  --accent-soft: #eff6ff;
  --accent-dark: #1d4ed8;
  --border: #e2e8f0;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06);
  --font-body: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-head: 'Playfair Display', Georgia, "Times New Roman", serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--font-body);
  background: var(--surface);
  color: var(--text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

.container {
  max-width: 720px;
  margin: 0 auto;
  padding: 48px 24px 64px;
}

header.top {
  text-align: center;
  padding-bottom: 32px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 40px;
}

header.top .icon {
  font-size: 2rem;
  margin-bottom: 8px;
}

header.top .kicker {
  display: inline-block;
  color: var(--accent);
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 12px;
}

header.top h1 {
  margin: 0;
  font-family: var(--font-head);
  font-size: 2.6rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.1;
}

header.top .subtitle {
  margin: 12px 0 0;
  color: var(--text-muted);
  font-size: 1rem;
}

header.top .quote {
  margin: 20px 0 0;
  font-family: var(--font-head);
  font-size: 1.05rem;
  font-style: italic;
  color: var(--text-muted);
  line-height: 1.5;
}

header.top .meta-line {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 16px;
  font-size: 0.78rem;
  color: var(--text-light);
}

.date-section {
  margin-bottom: 24px;
  padding-top: 8px;
}

.date-section:last-of-type {
  margin-bottom: 64px;
}

.date-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0 0 0;
  padding: 14px 18px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  color: #ffffff;
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  cursor: pointer;
  user-select: none;
  transition: background 0.2s ease;
}

.date-header:hover {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
}

.date-header h2 {
  margin: 0;
  font-family: var(--font-head);
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.date-header .count {
  color: #cbd5e1;
  font-size: 0.82rem;
  font-weight: 500;
  background: rgba(255,255,255,0.12);
  padding: 4px 10px;
  border-radius: 20px;
}

.date-divider {
  height: 2px;
  background: var(--border);
  margin: 0 0 32px;
  border-radius: 1px;
  transition: opacity 0.25s ease, margin 0.25s ease;
}

.date-divider.hidden {
  opacity: 0;
  margin: 0;
  height: 0;
}

.date-content {
  overflow: hidden;
  transition: max-height 0.35s ease, opacity 0.25s ease;
  max-height: 20000px;
  opacity: 1;
}

.date-content.collapsed {
  max-height: 0;
  opacity: 0;
}

.date-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 6px 12px;
  border-radius: 20px;
  background: rgba(255,255,255,0.15);
  color: #ffffff;
  border: 1px solid rgba(255,255,255,0.25);
  transition: transform 0.2s ease, background 0.2s ease;
}

.date-toggle .chevron {
  display: inline-block;
  transition: transform 0.25s ease;
}

.date-header[aria-expanded="false"] .date-toggle .chevron {
  transform: rotate(-90deg);
}

.date-header[aria-expanded="true"] .date-toggle .chevron {
  transform: rotate(0deg);
}

.category {
  margin-bottom: 36px;
}

.category h3 {
  margin: 0 0 18px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent);
  padding: 6px 10px;
  background: var(--accent-soft);
  display: inline-block;
  border-radius: 6px;
}

.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 22px 24px;
  margin-bottom: 16px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  border: 1px solid var(--border);
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
}

.card img {
  width: 100%;
  height: 160px;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 14px;
  background: var(--surface);
}

.card a.title {
  display: block;
  text-decoration: none;
  color: var(--text);
  font-family: var(--font-head);
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 10px;
  line-height: 1.35;
}

.card a.title:hover {
  color: var(--accent);
}

.meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.78rem;
  color: var(--text-light);
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.meta .source {
  font-weight: 600;
  color: var(--text-muted);
}

.meta .dot {
  width: 3px;
  height: 3px;
  background: var(--text-light);
  border-radius: 50%;
}

.meta .badge {
  display: inline-flex;
  align-items: center;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 20px;
  background: var(--accent-soft);
  color: var(--accent-dark);
}

.meta .badge.today {
  background: #dcfce7;
  color: #166534;
}

.meta .badge.yesterday {
  background: #fef9c3;
  color: #854d0e;
}

.summary {
  font-size: 0.98rem;
  color: var(--text);
  margin: 0;
  line-height: 1.6;
}

footer {
  text-align: center;
  padding: 48px 0 24px;
  color: var(--text-light);
  font-size: 0.8rem;
  border-top: 1px solid var(--border);
}

.empty {
  text-align: center;
  color: var(--text-muted);
  padding: 48px 0;
}

@media (max-width: 560px) {
  .container { padding: 32px 18px 48px; }
  header.top h1 { font-size: 2rem; }
  .date-header { flex-direction: column; align-items: flex-start; gap: 6px; }
  .date-header .count { align-self: flex-end; }
  .card { padding: 18px 20px; }
  .card a.title { font-size: 1.1rem; }
  .card img { height: 140px; }
  .meta { gap: 6px; }
}
""".strip()

    def card_html(item: Dict[str, Any], section_date: str) -> str:
        image_html = ""
        if item.get("image"):
            image_html = f'<img src="{item["image"]}" alt="" loading="lazy">'
        relative_badge = format_relative_badge(item.get("published", ""), section_date)
        badge_class = ""
        if relative_badge == "hoy":
            badge_class = "today"
        elif relative_badge == "ayer":
            badge_class = "yesterday"
        badge_html = f'<span class="badge {badge_class}">{relative_badge}</span>' if relative_badge else ""
        card_date = format_card_date(item.get("published", ""))
        return f"""
        <article class="card">
          {image_html}
          <a class="title" href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a>
          <div class="meta">
            <span class="source">{item['source']}</span>
            <span class="dot"></span>
            <span>{card_date}</span>
            {badge_html}
          </div>
          <p class="summary">{item.get('summary', '')}</p>
        </article>
        """

    sections = []
    sorted_dates = sorted(news_by_date.keys(), reverse=True)
    for idx, date in enumerate(sorted_dates):
        items = news_by_date[date]
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(item.get("category", "General"), []).append(item)
        categories_html = ""
        for category in sorted(grouped.keys()):
            categories_html += f"""
            <div class="category">
              <h3>{category}</h3>
              {"".join(card_html(i, date) for i in grouped[category])}
            </div>
            """
        expanded = "true" if idx == 0 else "false"
        collapsed_class = "" if idx == 0 else "collapsed"
        divider_class = "" if idx == 0 else "hidden"
        toggle_label = "Ocultar" if idx == 0 else "Mostrar"
        sections.append(f"""
        <section class="date-section" data-date="{date}">
          <div class="date-header" aria-expanded="{expanded}" tabindex="0" role="button">
            <h2>{format_date_header(date)}</h2>
            <span class="count">{len(items)} noticia{'s' if len(items) != 1 else ''}</span>
            <span class="date-toggle" aria-hidden="true"><span class="chevron">▾</span> {toggle_label}</span>
          </div>
          <div class="date-divider {divider_class}"></div>
          <div class="date-content {collapsed_class}">
            {categories_html}
          </div>
        </section>
        """)

    body = "".join(sections) if sections else "<p class='empty'>Aún no hay noticias para mostrar.</p>"

    return f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📰</text></svg>">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
  <div class="container">
    <header class="top">
      <span class="icon">📰</span>
      <span class="kicker">Daily Brief</span>
      <h1>{title}</h1>
      <p class="subtitle">Open banking, IA, innovación bancaria y productos financieros en Chile y Latam.</p>
      <p class="quote">{daily_quote}</p>
      <div class="meta-line">
        <span>Actualizado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</span>
      </div>
    </header>
    <main>
      {body}
    </main>
    <footer>
      Generado automáticamente · {datetime.now(timezone.utc).strftime('%Y')}
    </footer>
  </div>
  <script>
    (function() {{
      document.querySelectorAll('.date-header').forEach(function(header) {{
        function toggle() {{
          var expanded = header.getAttribute('aria-expanded') === 'true';
          var section = header.closest('.date-section');
          var divider = section.querySelector('.date-divider');
          var content = section.querySelector('.date-content');
          var toggleLabel = header.querySelector('.date-toggle');
          if (expanded) {{
            header.setAttribute('aria-expanded', 'false');
            if (divider) divider.classList.add('hidden');
            content.classList.add('collapsed');
            if (toggleLabel) toggleLabel.innerHTML = '<span class="chevron">▾</span> Mostrar';
          }} else {{
            header.setAttribute('aria-expanded', 'true');
            if (divider) divider.classList.remove('hidden');
            content.classList.remove('collapsed');
            if (toggleLabel) toggleLabel.innerHTML = '<span class="chevron">▾</span> Ocultar';
          }}
        }}
        header.addEventListener('click', toggle);
        header.addEventListener('keydown', function(e) {{
          if (e.key === 'Enter' || e.key === ' ') {{
            e.preventDefault();
            toggle();
          }}
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def main(regenerate_only: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen = set(load_json(SEEN_FILE, []))
    news_history = load_json(NEWS_FILE, [])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Fecha edición: {today}")

    daily_quote = DAILY_QUOTES[datetime.now(timezone.utc).day % len(DAILY_QUOTES)]

    if not regenerate_only:
        new_items = collect_news()
        new_items = select_items_chile_priority(new_items, total_limit=10, max_global=3)

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

        for item in new_items:
            news_history.append(item)
            seen.add(item["id"])
    else:
        print("Modo regeneración: solo reconstruye HTML desde historial.")

    unique_history: Dict[str, Dict[str, Any]] = {}
    for item in news_history:
        key = item.get("id") or seen_key(item)
        if key not in unique_history:
            unique_history[key] = item
    news_history = list(unique_history.values())

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for item in news_history:
        by_date.setdefault(item["date"], []).append(item)

    HTML_FILE.write_text(build_html(by_date, daily_quote=daily_quote), encoding="utf-8")
    save_json(SEEN_FILE, sorted(seen))
    save_json(NEWS_FILE, news_history)
    print(f"Total histórico único: {len(news_history)}")
    print(f"HTML escrito: {HTML_FILE}")


if __name__ == "__main__":
    regenerate_only = "--regenerate-only" in sys.argv
    main(regenerate_only=regenerate_only)

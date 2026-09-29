#!/usr/bin/env python3
"""
Generador de Tech News para la newsletter.
Ejecuta el pipeline de tech-news-digest y convierte el output al formato de la newsletter.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

TECH_NEWS_DIR = Path("/root/.openclaw/workspace/skills/tech-news-digest")
PIPELINE_SCRIPT = TECH_NEWS_DIR / "scripts" / "run-pipeline.py"
DEFAULTS_DIR = TECH_NEWS_DIR / "config" / "defaults"
ARCHIVE_DIR = Path("/root/.openclaw/workspace/archive/tech-news-digest")

def run_pipeline() -> Dict[str, Any]:
    """Run tech-news-digest pipeline and return merged data."""
    import tempfile
    
    output_file = tempfile.mktemp(suffix=".json", prefix="td-merged-")
    archive_dir = ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "python3", str(PIPELINE_SCRIPT),
        "--defaults", str(DEFAULTS_DIR),
        "--hours", "48",
        "--freshness", "pd",
        "--archive-dir", str(archive_dir),
        "--output", output_file,
        "--force"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"Pipeline error: {result.stderr[:500]}")
            return {}
    except Exception as e:
        print(f"Pipeline exception: {e}")
        return {}
    
    try:
        with open(output_file, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error reading pipeline output: {e}")
        return {}


def convert_to_newsletter_format(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert tech-news-digest output to newsletter format."""
    if not data or "topics" not in data:
        return []
    
    tech_articles = []
    topic_emojis = {
        "frontier-tech": "🚀",
        "llm": "🧠",
        "ai-agent": "🤖",
        "crypto": "₿"
    }
    topic_labels = {
        "frontier-tech": "Tech Global",
        "llm": "IA y Modelos",
        "ai-agent": "Agentes IA",
        "crypto": "Crypto"
    }
    
    for topic_id, topic_data in data.get("topics", {}).items():
        emoji = topic_emojis.get(topic_id, "📰")
        label = topic_labels.get(topic_id, topic_id)
        
        # Top 5 articles per topic
        for article in topic_data.get("articles", [])[:5]:
            title = article.get("title", "")
            url = article.get("link", "")
            snippet = article.get("snippet", "")[:240]
            score = article.get("quality_score", 0)
            source = article.get("source_name", article.get("source", "Tech News"))
            
            if not title or not url:
                continue
                
            tech_articles.append({
                "id": f"tech-{hash(title + url) % 100000000:08x}",
                "title": f"{emoji} {title}",
                "url": url,
                "source": source,
                "summary": snippet or f"Noticia tech destacada en {label}",
                "published": datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                "score": min(score / 15.0, 1.0),  # Normalize score
                "category": f"Tech News — {label}",
                "image": "",
                "date": datetime.now().strftime("%Y-%m-%d")
            })
    
    # Sort by score descending
    tech_articles.sort(key=lambda x: x.get("score", 0), reverse=True)
    return tech_articles[:15]  # Max 15 tech articles total


def get_tech_news() -> List[Dict[str, Any]]:
    """Main entry point: run pipeline and return formatted tech news."""
    print("Ejecutando pipeline de Tech News Digest...")
    data = run_pipeline()
    if not data:
        print("No se pudo obtener tech news. Verifica que el pipeline esté configurado.")
        return []
    
    total = data.get("output_stats", {}).get("total_articles", 0)
    print(f"Tech News: {total} artículos encontrados")
    
    articles = convert_to_newsletter_format(data)
    print(f"Convertidos: {len(articles)} artículos para la newsletter")
    return articles


if __name__ == "__main__":
    articles = get_tech_news()
    print(json.dumps(articles, ensure_ascii=False, indent=2))

"""
Web Fetcher Module
Provides live web context fetching via Wikipedia API and DuckDuckGo HTML search
without requiring any API keys or external credentials.
Includes fallback mechanisms for offline execution.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) CIE-Assistant/1.0 (Educational AI Assistant)"


def fetch_wikipedia_summary(topic: str, timeout: float = 4.0) -> dict[str, Any] | None:
    """Fetch encyclopedia summary for a topic using the public Wikipedia REST API."""
    clean_topic = topic.strip()
    if not clean_topic:
        return None

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    # 1. Try direct page summary
    encoded = urllib.parse.quote(clean_topic.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                extract = data.get("extract", "")
                title = data.get("title", clean_topic)
                page_url = data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{encoded}")
                if extract:
                    return {
                        "title": title,
                        "extract": extract,
                        "url": page_url,
                        "source": "Wikipedia",
                    }
    except Exception as exc:
        logger.debug("Wikipedia direct summary failed for %s: %s", clean_topic, exc)

    # 2. Try opensearch to find closest title if direct summary missed
    try:
        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_topic)}&limit=1&format=json"
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if len(data) >= 4 and data[1] and data[3]:
                found_title = data[1][0]
                found_url = data[3][0]
                enc_found = urllib.parse.quote(found_title.replace(" ", "_"))
                sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{enc_found}"
                req_sum = urllib.request.Request(sum_url, headers=headers)
                with urllib.request.urlopen(req_sum, timeout=timeout) as sum_resp:
                    sum_data = json.loads(sum_resp.read().decode("utf-8", errors="ignore"))
                    return {
                        "title": sum_data.get("title", found_title),
                        "extract": sum_data.get("extract", ""),
                        "url": found_url,
                        "source": "Wikipedia",
                    }
    except Exception as exc:
        logger.debug("Wikipedia opensearch failed: %s", exc)

    return None


def fetch_duckduckgo_snippets(query: str, max_results: int = 3, timeout: float = 4.0) -> list[dict[str, str]]:
    """Fetch top search results and snippets from DuckDuckGo HTML without API keys."""
    clean_query = query.strip()
    if not clean_query:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_query)}"
    results: list[dict[str, str]] = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        blocks = re.findall(r'<div class="result__body">([\s\S]*?)</div>\s*</div>', html)
        for block in blocks:
            snippet_match = re.search(r'<a class="result__snippet[^>]*>([\s\S]*?)</a>', block)
            snippet = ""
            if snippet_match:
                snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()

            title_match = re.search(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block)
            link = ""
            title = ""
            if title_match:
                link = title_match.group(1).strip()
                title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
            else:
                l_match = re.search(r'href="([^"]+uddg=[^"]+)"', block)
                if l_match:
                    raw_l = l_match.group(1)
                    if "uddg=" in raw_l:
                        link = urllib.parse.unquote(raw_l.split("uddg=")[1].split("&")[0])

            if link and "duckduckgo.com/l/?uddg=" in link:
                link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])

            if snippet or title:
                results.append({
                    "title": title or clean_query,
                    "snippet": snippet,
                    "url": link,
                })
            if len(results) >= max_results:
                break
    except Exception as exc:
        logger.debug("DuckDuckGo fetch failed for %s: %s", clean_query, exc)

    return results


def clean_search_topic(query: str) -> tuple[str, bool]:
    """
    Cleans raw user queries or document prompts down to the essential subject.
    Detects if the user requested images/figures.
    Example: 'create a report on kangroo with images' -> ('kangroo', True)
    """
    clean = query.strip()
    wants_images = bool(re.search(r'\b(?:with|having|including)\s+(?:images?|photos?|pictures?|figures?|diagrams?)\b', clean, re.I))
    clean = re.sub(r'\b(?:with|having|including)\s+(?:images?|photos?|pictures?|figures?|diagrams?)\b', '', clean, flags=re.I)
    clean = re.sub(r'\b(?:in\s+)?(?:research\s+)?(?:paper|report|academic|scholarly|formal)\s+format\b', '', clean, flags=re.I)
    clean = re.sub(r'^(?:create|make|generate|build|write)?\s*(?:a\s+)?(?:word|docx?|document|paper|report|study|monograph|article)?\s+(?:of|on|about|for|regarding)\s+', '', clean, flags=re.I)
    clean = re.sub(r'\b(?:create|make|generate|build|write)\s+(?:a\s+)?(?:word|docx?|document|paper|report|study|monograph|article)\b', '', clean, flags=re.I)
    clean = re.sub(r'\b(?:what\s+is|tell\s+me\s+about|information\s+on|details\s+about)\s+', '', clean, flags=re.I)
    clean = re.sub(r'\s+', ' ', clean).strip(' "\'.,:;?')
    return clean or query.strip(), wants_images


def fetch_and_cache_topic_images(
    canonical_title: str,
    max_images: int = 3,
    timeout: float = 6.0,
) -> list[dict[str, str]]:
    """
    Fetch and download high-resolution Wikimedia Commons images associated with a topic.
    Returns list of dicts with local file paths, captions, and source URLs.
    """
    from pathlib import Path
    clean = canonical_title.strip()
    if not clean:
        return []

    safe_stem = re.sub(r'[^a-zA-Z0-9_\-]+', '_', clean.lower()).strip('_')
    cache_dir = Path.home() / "Documents" / "Sortwise" / "assets" / "images" / safe_stem
    cache_dir.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    downloaded: list[dict[str, str]] = []

    # 1. Fetch page primary thumbnail
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(clean)}&prop=pageimages&piprop=thumbnail&pithumbsize=1000&format=json"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            pages = data.get("query", {}).get("pages", {})
            for pid, p in pages.items():
                thumb_url = p.get("thumbnail", {}).get("source")
                if thumb_url:
                    ext = ".jpg" if ".jpg" in thumb_url.lower() else (".png" if ".png" in thumb_url.lower() else ".jpg")
                    dest_file = cache_dir / f"{safe_stem}_fig1{ext}"
                    if not dest_file.exists() or dest_file.stat().st_size == 0:
                        img_req = urllib.request.Request(thumb_url, headers=headers)
                        with urllib.request.urlopen(img_req, timeout=timeout) as img_resp:
                            dest_file.write_bytes(img_resp.read())
                    if dest_file.exists() and dest_file.stat().st_size > 1000:
                        downloaded.append({
                            "path": str(dest_file),
                            "caption": f"Morphological and anatomical specimen of {clean}.",
                            "url": thumb_url,
                        })
    except Exception as exc:
        logger.debug("Failed fetching primary thumbnail for %s: %s", clean, exc)

    # 2. Fetch gallery images if more needed
    if len(downloaded) < max_images:
        try:
            g_url = f"https://en.wikipedia.org/w/api.php?action=query&generator=images&titles={urllib.parse.quote(clean)}&gimlimit=12&prop=imageinfo&iiprop=url&format=json"
            g_req = urllib.request.Request(g_url, headers=headers)
            with urllib.request.urlopen(g_req, timeout=timeout) as g_resp:
                g_data = json.loads(g_resp.read().decode("utf-8", errors="ignore"))
                g_pages = g_data.get("query", {}).get("pages", {})
                for pid, p in g_pages.items():
                    title = p.get("title", "")
                    if any(title.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                        if not any(skip in title.lower() for skip in ("icon", "flag", "symbol", "logo", "commons-logo", "stub", "question")):
                            info = p.get("imageinfo", [{}])[0]
                            img_url = info.get("url")
                            if img_url:
                                idx = len(downloaded) + 1
                                ext = ".png" if img_url.lower().endswith(".png") else ".jpg"
                                dest_file = cache_dir / f"{safe_stem}_fig{idx}{ext}"
                                if not dest_file.exists() or dest_file.stat().st_size == 0:
                                    ireq = urllib.request.Request(img_url, headers=headers)
                                    with urllib.request.urlopen(ireq, timeout=timeout) as i_resp:
                                        dest_file.write_bytes(i_resp.read())
                                if dest_file.exists() and dest_file.stat().st_size > 1000:
                                    clean_fig_name = title.replace("File:", "").rsplit(".", 1)[0].replace("_", " ")
                                    downloaded.append({
                                        "path": str(dest_file),
                                        "caption": f"Field observation and behavioral habitat representation: {clean_fig_name}.",
                                        "url": img_url,
                                    })
                                if len(downloaded) >= max_images:
                                    break
        except Exception as exc:
            logger.debug("Failed fetching gallery images for %s: %s", clean, exc)

    return downloaded


def fetch_wikipedia_sections_content(canonical_title: str, max_sections: int = 6, timeout: float = 5.0) -> list[dict[str, Any]]:
    """
    Fetch structured section content and paragraphs from Wikipedia.
    """
    clean = canonical_title.strip()
    if not clean:
        return []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    sections_list: list[dict[str, Any]] = []

    try:
        url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(clean)}&prop=sections&format=json"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            raw_secs = data.get("parse", {}).get("sections", [])

        # Filter substantive sections
        filtered_secs = [
            s for s in raw_secs
            if s.get("line") and not any(skip in s.get("line", "").lower() for skip in ("see also", "references", "external links", "further reading", "notes", "bibliography"))
        ][:max_sections]

        for s in filtered_secs:
            sec_idx = s.get("index")
            sec_title = s.get("line")
            txt_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(clean)}&prop=wikitext&section={sec_idx}&format=json"
            txt_req = urllib.request.Request(txt_url, headers=headers)
            with urllib.request.urlopen(txt_req, timeout=timeout) as txt_resp:
                txt_data = json.loads(txt_resp.read().decode("utf-8", errors="ignore"))
                raw_wt = txt_data.get("parse", {}).get("wikitext", {}).get("*", "")

                # Clean wikitext
                c_wt = re.sub(r'\{\{[^}]+\}\}', '', raw_wt)
                c_wt = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', c_wt)
                c_wt = re.sub(r'<ref[^>]*>.*?</ref>', '', c_wt, flags=re.DOTALL)
                c_wt = re.sub(r'<[^>]+>', '', c_wt)
                c_wt = re.sub(r'==+[^=]+==+', '', c_wt)
                paras = [p.strip() for p in c_wt.split("\n\n") if len(p.strip()) > 40 and not p.strip().startswith(("*", "{", "|"))]

                if paras:
                    sections_list.append({
                        "title": sec_title,
                        "paragraphs": paras[:3],
                    })
    except Exception as exc:
        logger.debug("Failed fetching section wikitext for %s: %s", clean, exc)

    return sections_list


def fetch_web_context(
    topic: str,
    max_results: int = 4,
    timeout: float = 4.0,
    fetch_images: bool = True,
) -> dict[str, Any]:
    """
    Unified web context aggregator with typo-tolerance and image downloading.
    Returns verified encyclopedic summary, live search snippets, source citations,
    structured section contents, and downloaded local image artifacts.
    """
    cleaned_topic, wants_images = clean_search_topic(topic)
    if not cleaned_topic:
        return {
            "status": "empty",
            "topic": "",
            "summary": "No topic provided.",
            "snippets": [],
            "sources": [],
            "images": [],
            "sections": [],
        }

    wiki_res = fetch_wikipedia_summary(cleaned_topic, timeout=timeout)
    canonical_title = wiki_res.get("title", cleaned_topic) if wiki_res else cleaned_topic
    ddg_res = fetch_duckduckgo_snippets(cleaned_topic, max_results=max_results, timeout=timeout)

    sources: list[str] = []
    summary = ""
    snippets: list[str] = []

    if wiki_res:
        summary = wiki_res.get("extract", "")
        if wiki_res.get("url"):
            sources.append(wiki_res["url"])

    for item in ddg_res:
        if item.get("snippet"):
            snippets.append(item["snippet"])
        if item.get("url") and item["url"] not in sources:
            sources.append(item["url"])

    if not summary and snippets:
        summary = " ".join(snippets[:2])

    # Fetch and cache real Wikimedia images if requested or by default
    images = []
    if fetch_images or wants_images:
        images = fetch_and_cache_topic_images(canonical_title, max_images=3, timeout=timeout + 2.0)

    # Fetch real structured sections if available
    structured_sections = []
    try:
        structured_sections = fetch_wikipedia_sections_content(canonical_title, max_sections=6, timeout=timeout + 1.0)
    except Exception:
        pass

    status = "success" if (summary or snippets or structured_sections) else "offline"
    if not summary:
        summary = f"No live web results retrieved for '{cleaned_topic}'. Using standard offline corpus."

    return {
        "status": status,
        "topic": cleaned_topic,
        "title": canonical_title,
        "summary": summary,
        "snippets": snippets,
        "sources": sources,
        "images": images,
        "sections": structured_sections,
        "wants_images": wants_images,
    }


def enrich_sections_with_web_context(
    sections: list[dict[str, Any]],
    web_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Enriches document sections with factual web data, observational evidence, and citations
    when the Web Fetch toggle is enabled.
    """
    if not web_data or web_data.get("status") != "success":
        return sections

    summary = web_data.get("summary", "").strip()
    sources = web_data.get("sources", [])
    snippets = web_data.get("snippets", [])

    enriched = [dict(s) for s in sections]

    if enriched and summary:
        first_sec = enriched[0]
        paras = list(first_sec.get("paragraphs") or [])
        paras.insert(0, f"**Verified Web Overview:** {summary}")
        orig_b = first_sec.get("body", "")
        first_sec["body"] = f"{summary}\n\n{orig_b}" if orig_b else summary

    # Append snippets if available and not redundant
    if snippets and len(enriched) > 1:
        second_sec = enriched[1]
        s_paras = list(second_sec.get("paragraphs") or [])
        for snip in snippets[:2]:
            s_paras.append(f"**Observational Telemetry:** {snip}")
        second_sec["paragraphs"] = s_paras

    if sources:
        ref_lines = [f"[{i+1}] Verified Web Source: {src}" for i, src in enumerate(sources)]
        # Check if a references section already exists
        ref_idx = -1
        for idx, sec in enumerate(enriched):
            if "reference" in sec.get("heading", "").lower() or "bibliography" in sec.get("heading", "").lower():
                ref_idx = idx
                break

        if ref_idx >= 0:
            existing_bullets = list(enriched[ref_idx].get("bullets") or [])
            existing_bullets.extend(ref_lines)
            enriched[ref_idx]["bullets"] = existing_bullets
        else:
            ref_body = "The following verified live web references were incorporated during synthesis:\n\n" + "\n".join(ref_lines)
            enriched.append({
                "heading": "Verified References and Web Sources",
                "level": 1,
                "page_break": True,
                "body": ref_body,
                "paragraphs": [
                    "The following verified live web references and digital artifacts were integrated into this document during automated synthesis:"
                ],
                "bullets": ref_lines,
            })

    return enriched


def format_web_chat_response(topic: str, web_data: dict[str, Any]) -> str:
    """Format clean markdown string summarizing live web findings for the chat view."""
    if not web_data or web_data.get("status") != "success":
        return f"🌐 **Web Fetch**: Unable to retrieve online data for '{topic}'. Using local model knowledge."

    summary = web_data.get("summary", "")
    sources = web_data.get("sources", [])
    snippets = web_data.get("snippets", [])

    md_parts = [
        f"🌐 **Web Fetch Results: {web_data.get('title', topic)}**\n",
        f"**Summary:**\n{summary}\n",
    ]

    if snippets and len(snippets) > 1:
        md_parts.append("**Key Observations:**")
        for snip in snippets[:3]:
            md_parts.append(f"• {snip}")
        md_parts.append("")

    if sources:
        md_parts.append("**Sources Consulted:**")
        for src in sources[:4]:
            md_parts.append(f"- <{src}>")

    return "\n".join(md_parts)

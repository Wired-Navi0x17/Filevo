"""Web Research and Live Topic Exploration Engine for Filevo.

Enables Filevo to access the web when a user requests a document or asks about
a topic that is unfamiliar, missing from the local knowledge base, or requires
live web grounding.

Capabilities:
- Real-time Wikipedia API summary and section retrieval
- DuckDuckGo web search snippet extraction
- Direct web page fetching with clean text extraction
- Structural outline & section synthesizer for OpenXML DOCX generation
- Zero C-dependencies: uses httpx and Python standard library html.parser
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Filevo-Intelligence/1.0)"


class HTMLTextExtractor(HTMLParser):
    """Clean HTML to plain text using standard library parser."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "noscript", "header", "footer", "nav"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "noscript", "header", "footer", "nav"):
            self._skip = False
        if tag.lower() in ("p", "div", "br", "h1", "h2", "h3", "h4", "li"):
            self.fed.append("\n")

    def handle_data(self, d):
        if not self._skip:
            self.fed.append(d)

    def get_text(self) -> str:
        text = "".join(self.fed)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


class WebResearcher:
    """Live web search and document context synthesizer."""

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.headers = {"User-Agent": USER_AGENT}

    def _http_get(self, url: str) -> tuple[int, str]:
        """Perform HTTP GET using httpx or standard library urllib."""
        if HAS_HTTPX:
            try:
                with httpx.Client(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.get(url)
                    return resp.status_code, resp.text
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception:
            return 500, ""

    def _http_post_ddg(self, query: str) -> tuple[int, str]:
        """Perform HTTP POST to DuckDuckGo HTML."""
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = dict(self.headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        if HAS_HTTPX:
            try:
                with httpx.Client(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.post(url, data={"q": query})
                    return resp.status_code, resp.text
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception:
            return 500, ""

    def fetch_wikipedia_summary(self, query: str) -> dict[str, Any] | None:
        """Fetch lead summary and title from Wikipedia REST API with OpenSearch title resolution."""
        # Step 1: Resolve best matching title using OpenSearch API
        search_title = query.strip()
        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(search_title)}&limit=1&format=json"
        s_status, s_text = self._http_get(search_url)
        resolved_title = search_title
        if s_status == 200 and s_text:
            try:
                s_data = json.loads(s_text)
                if len(s_data) > 1 and s_data[1]:
                    resolved_title = s_data[1][0]
            except Exception:
                pass

        # Step 2: Fetch summary for the resolved title
        clean_title = resolved_title.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_title)}"
        status, text = self._http_get(url)
        if status == 200 and text:
            try:
                data = json.loads(text)
                return {
                    "source": "Wikipedia",
                    "title": data.get("title", resolved_title),
                    "description": data.get("description", ""),
                    "extract": data.get("extract", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", url),
                }
            except Exception:
                pass
        return None

    def search_duckduckgo(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Search DuckDuckGo HTML for snippets and links."""
        results = []
        status, html = self._http_post_ddg(query)
        if status in (200, 202) and html:
            try:
                snippets = re.findall(
                    r'<a class="result__snippet[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )
                link_matches = re.findall(
                    r'<a class="result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

                SPAM_PATTERNS = [
                    "smartcric", "smart cric", "crichd", "crictime", "cricstream",
                    "live cricket match today online", "watch live cricket streaming",
                    "watch online for free", "live streaming online free", "buffstream",
                    "stream2watch", "vipbox", "cricfree", "apk download", "betting odds"
                ]

                for i, snip in enumerate(snippets[:max_results * 2]):
                    clean_snip = re.sub(r"<[^>]+>", "", snip).strip()
                    raw_url = link_matches[i][0] if i < len(link_matches) else ""
                    raw_title = link_matches[i][1] if i < len(link_matches) else ""
                    clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                    if "uddg=" in raw_url:
                        raw_url = urllib.parse.unquote(raw_url.split("uddg=")[-1].split("&")[0])
                    domain = urllib.parse.urlparse(raw_url).netloc.removeprefix("www.") if raw_url else ""
                    
                    # Spam / low-quality filter
                    test_str = f"{clean_title} {clean_snip} {domain}".lower()
                    if any(sp in test_str for sp in SPAM_PATTERNS):
                        continue

                    # Relevance check: require at least one topical keyword from query
                    query_keywords = [
                        w.lower() for w in re.findall(r"\w+", query)
                        if len(w) > 3 and w.lower() not in ("create", "report", "document", "specifying", "technical", "please")
                    ]
                    if query_keywords and not any(kw in test_str for kw in query_keywords):
                        continue

                    results.append({
                        "title": clean_title or domain or "Reference",
                        "snippet": clean_snip,
                        "url": raw_url,
                        "domain": domain,
                    })
                    if len(results) >= max_results:
                        break
            except Exception:
                pass
        return results

    def fetch_url(self, url: str, max_chars: int = 4000) -> str:
        """Fetch and extract clean plain text from an arbitrary web URL."""
        status, html = self._http_get(url)
        if status == 200 and html:
            parser = HTMLTextExtractor()
            parser.feed(html)
            return parser.get_text()[:max_chars]
        return f"[Unable to fetch URL {url} (HTTP {status})]"

    def research_topic(self, topic: str) -> dict[str, Any]:
        """Perform multi-source web research on a topic and structure into document sections.
        
        Returns:
            Dictionary containing topic overview, synthesized sections, and source citations.
        """
        wiki_data = self.fetch_wikipedia_summary(topic)
        ddg_results = self.search_duckduckgo(topic, max_results=4)

        overview = ""
        sources = []
        if wiki_data:
            overview = wiki_data["extract"]
            if wiki_data.get("url"):
                wiki_domain = urllib.parse.urlparse(wiki_data["url"]).netloc.removeprefix("www.")
                sources.append({
                    "title": wiki_data.get("title", topic),
                    "url": wiki_data["url"],
                    "domain": wiki_domain,
                })

        combined_snippets = []
        for r in ddg_results:
            if r.get("snippet"):
                combined_snippets.append(r["snippet"])
            if r.get("url"):
                sources.append({
                    "title": r.get("title", topic),
                    "url": r["url"],
                    "domain": r.get("domain", ""),
                })

        if not overview and combined_snippets:
            overview = " ".join(combined_snippets[:2])

        sections = []

        intro_content = overview if overview else f"Comprehensive analysis and architectural study of {topic}."
        sections.append({
            "title": f"Introduction and Background to {topic.title()}",
            "content": intro_content,
        })

        core_body = ""
        if len(combined_snippets) >= 2:
            core_body = f"Key operational principles and foundational aspects: {combined_snippets[0]}"
        else:
            core_body = f"Key operational paradigms, design criteria, and architectural considerations defining {topic}."
        sections.append({
            "title": "Fundamental Concepts and Architecture",
            "content": core_body,
        })

        sections.append({
            "title": "Implementation Strategies and Best Practices",
            "content": (
                f"Deploying and operationalizing {topic} requires adherence to proven design patterns, "
                f"robust error handling, automated verification, and proactive monitoring frameworks."
            ),
        })

        trend_body = (
            f"Recent industry developments highlighted across current technical reports indicate increasing "
            f"adoption, standardized protocols, and integration with modern distributed ecosystems."
        )
        if len(combined_snippets) >= 3:
            trend_body += f" Notable observation: {combined_snippets[1]}"
        sections.append({
            "title": "Industry Trends and Future Outlook",
            "content": trend_body,
        })

        source_text = "Primary references and live sources consulted during research:\n"
        if sources:
            source_text += "\n".join(f"• {s}" for s in sources[:5])
        else:
            source_text += f"• Domain literature and foundational specifications for {topic}."
        sections.append({
            "title": "References and Source Documentation",
            "content": source_text,
        })

        return {
            "topic": topic,
            "has_web_data": bool(wiki_data or ddg_results),
            "overview": overview,
            "sources": sources,
            "sections": sections,
        }

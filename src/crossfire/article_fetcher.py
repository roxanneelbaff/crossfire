"""Article fetching from Al Jazeera, The Atlantic, and National Review."""

import re

import requests
from bs4 import BeautifulSoup

# Matches real Al Jazeera opinion article paths, e.g. /opinions/2026/6/9/some-slug
ARTICLE_PATH_RE = re.compile(r"^/opinions?/\d{4}/\d{1,2}/\d{1,2}/.+")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_aljazeera_list(limit: int = 8) -> list:
    """Return list of latest opinion articles from Al Jazeera."""
    url = "https://www.aljazeera.com/opinion/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen_urls = set()

    for card in soup.select("article, .article-card, .article-trending__item"):
        # Pick the <a> that actually points at an article (not the
        # "/opinion/" category badge link, which is usually first in DOM order).
        a_tag = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            if ARTICLE_PATH_RE.match(href):
                a_tag = a
                break
        if not a_tag:
            continue
        href = a_tag["href"]
        full_url = "https://www.aljazeera.com" + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title_tag = card.find(["h2", "h3", "h4"])
        title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
        if not title:
            continue

        date_tag = card.find("time")
        date = date_tag.get("datetime", date_tag.get_text(strip=True)) if date_tag else ""

        articles.append({"title": title, "url": full_url, "date": date})
        if len(articles) >= limit:
            break

    # Fallback: scan all links if structured cards didn't yield results
    if not articles:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ARTICLE_PATH_RE.match(href):
                full_url = "https://www.aljazeera.com" + href if href.startswith("/") else href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                title = a.get_text(strip=True)
                if len(title) > 10:
                    articles.append({"title": title, "url": full_url, "date": ""})
                    if len(articles) >= limit:
                        break

    return articles


def fetch_aljazeera_article(url: str) -> dict:
    """Fetch and extract full article content from an Al Jazeera URL."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()
    if not author:
        author_link = soup.select_one("a[href*='/author/']")
        if author_link:
            author = author_link.get_text(strip=True)
    if not author:
        author_tag = soup.select_one(".article-author-name, .author-link")
        if author_tag:
            author = author_tag.get_text(strip=True)

    date = ""
    for meta_name in ("article:published_time", "publishedDate"):
        meta_date = soup.find("meta", attrs={"property": meta_name}) or soup.find(
            "meta", attrs={"name": meta_name}
        )
        if meta_date and meta_date.get("content"):
            date = meta_date["content"].strip()
            break
    if not date:
        date_tag = soup.find("time")
        if date_tag:
            date = date_tag.get("datetime", date_tag.get_text(strip=True))

    # Extract body — try multiple selectors
    body = ""
    body_selectors = [
        ".wysiwyg--all-content",
        ".article__body",
        "article .wysiwyg",
        ".article-body",
        "[class*='article-body']",
        "article",
    ]
    for sel in body_selectors:
        container = soup.select_one(sel)
        if container:
            # Remove unwanted elements
            for tag in container.select(
                "script, style, aside, .advertisement, .related-articles, "
                ".social-share, nav, [class*='related'], [class*='promo']"
            ):
                tag.decompose()
            paragraphs = container.find_all("p")
            body = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            if len(body) > 200:
                break

    return {
        "title": title,
        "author": author,
        "date": date,
        "body": body,
        "url": url,
        "source": "Al Jazeera",
        "domain": "aljazeera.com",
    }


def fetch_atlantic_list(limit: int = 8) -> list:
    """Return list of latest articles from The Atlantic via RSS."""
    resp = requests.get("https://www.theatlantic.com/feed/all/", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")

    articles = []
    for entry in soup.find_all("entry")[:limit]:
        link_tag = entry.find("link")
        url = link_tag["href"] if link_tag and link_tag.get("href") else ""
        if not url:
            continue
        # Strip UTM params
        url = url.split("?")[0]

        title_tag = entry.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        date_tag = entry.find("updated") or entry.find("published")
        date = date_tag.get_text(strip=True) if date_tag else ""

        articles.append({"title": title, "url": url, "date": date})

    return articles


def fetch_atlantic_article(url: str) -> dict:
    """Fetch full article content from The Atlantic via its RSS feed entry."""
    # The Atlantic blocks direct page scraping; pull full text from the RSS feed
    # where each <content> element contains the complete article HTML.
    feed_url = "https://www.theatlantic.com/feed/all/"
    clean_url = url.split("?")[0].rstrip("/")

    resp = requests.get(feed_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")

    entry = None
    for e in soup.find_all("entry"):
        link = e.find("link")
        href = (link["href"] if link and link.get("href") else "").split("?")[0].rstrip("/")
        if href == clean_url:
            entry = e
            break

    if entry is None:
        raise ValueError(f"Article not found in Atlantic RSS feed: {url}")

    title_tag = entry.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = entry.find("author")
    author = author_tag.find("name").get_text(strip=True) if author_tag and author_tag.find("name") else ""

    date_tag = entry.find("updated") or entry.find("published")
    date = date_tag.get_text(strip=True) if date_tag else ""

    # First <content> tag holds the full article HTML
    content_tags = entry.find_all("content")
    body = ""
    for ct in content_tags:
        import html as _html
        inner = BeautifulSoup(_html.unescape(ct.decode_contents()), "html.parser")
        paragraphs = inner.find_all("p")
        candidate = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        if len(candidate) > len(body):
            body = candidate

    return {
        "title": title,
        "author": author,
        "date": date,
        "body": body,
        "url": url,
        "source": "The Atlantic",
        "domain": "theatlantic.com",
    }


def fetch_nationalreview_list(limit: int = 8) -> list:
    """Return list of latest articles from National Review via RSS."""
    resp = requests.get("https://www.nationalreview.com/feed/", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")

    articles = []
    for item in soup.find_all("item")[:limit]:
        link_tag = item.find("link")
        url = link_tag.get_text(strip=True) if link_tag else ""
        if not url:
            continue

        title_tag = item.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        date_tag = item.find("pubDate")
        date = date_tag.get_text(strip=True) if date_tag else ""

        articles.append({"title": title, "url": url, "date": date})

    return articles


def fetch_nationalreview_article(url: str) -> dict:
    """Fetch full article content from National Review via its AMP page."""
    # NR's main pages are JS-rendered; the AMP version returns static HTML.
    amp_url = url.rstrip("/") + "/amp/"
    resp = requests.get(amp_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = og["content"].strip()
    if " | " in title:
        title = title.split(" | ")[0].strip()

    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()
    if not author:
        for sel in ["[class*='author']", "[class*='byline']", "[rel='author']"]:
            tag = soup.select_one(sel)
            if tag:
                author = tag.get_text(strip=True)
                # Remove "By" prefix artifacts e.g. "ByJohn Smith"
                if author.startswith("By"):
                    author = author[2:].strip()
                break

    date = ""
    meta_date = soup.find("meta", attrs={"property": "article:published_time"})
    if meta_date and meta_date.get("content"):
        date = meta_date["content"].strip()
    if not date:
        t = soup.find("time")
        if t:
            date = t.get("datetime", t.get_text(strip=True))

    paragraphs = soup.find_all("p")
    body = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    return {
        "title": title,
        "author": author,
        "date": date,
        "body": body,
        "url": url,
        "source": "National Review",
        "domain": "nationalreview.com",
    }

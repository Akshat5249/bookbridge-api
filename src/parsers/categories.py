"""Pure parsing of public category sidebar links."""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.exceptions import UpstreamParseError
from src.schemas.books import Category


@dataclass(frozen=True)
class CategoryLink:
    """Public category and its verified upstream URL."""

    category: Category
    url: str


def parse_categories(html: str, page_url: str) -> tuple[CategoryLink, ...]:
    """Read only nested category entries, excluding the top-level Books node."""
    links = []
    seen = set()
    for anchor in BeautifulSoup(html, "html.parser").select("div.side_categories ul li ul li a"):
        name = anchor.get_text(" ", strip=True)
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        url = urljoin(page_url, str(anchor.get("href", "")))
        if not name or not slug or slug == "books" or slug in seen:
            continue
        if not re.fullmatch(
            r"/catalogue/category/books/[a-z0-9-]+_\d+/index\.html", urlsplit(url).path
        ):
            raise UpstreamParseError()
        links.append(CategoryLink(Category(name=name, slug=slug), url))
        seen.add(slug)
    if not links:
        raise UpstreamParseError()
    return tuple(links)

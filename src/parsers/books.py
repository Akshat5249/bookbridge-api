"""Deterministic HTML extraction with no network or clock dependencies."""

import logging
import re
from decimal import Decimal
from typing import Literal
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from src.exceptions import UpstreamParseError
from src.schemas.books import BookDetail, BookSummary

logger = logging.getLogger(__name__)
BOOK_ID = re.compile(r"^[a-z0-9][a-z0-9-]*_[0-9]+$")
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def text(element: Tag | None) -> str:
    """Normalize whitespace in a selected element."""
    return element.get_text(" ", strip=True) if element else ""


def price(element: Tag | None) -> Decimal:
    """Parse GBP including the documented mojibake pound sign."""
    raw = text(element)
    match = re.fullmatch(r"(?:Â)?£\s*(\d+(?:\.\d{1,2})?)", raw)
    if not match:
        raise UpstreamParseError()
    return Decimal(match[1]).quantize(Decimal("0.01"))


def rating(element: Tag | None) -> int:
    """Convert one of the five documented rating classes."""
    for token in element.get("class", []) if element else []:
        if token in RATINGS:
            return RATINGS[token]
    raise UpstreamParseError()


def availability(raw: str) -> Literal["in_stock", "out_of_stock", "unknown"]:
    """Normalize stock wording without confusing out-of-stock with in-stock."""
    raw = raw.casefold()
    if "out of stock" in raw:
        return "out_of_stock"
    return "in_stock" if "in stock" in raw else "unknown"


def image_url(element: Tag | None, page_url: str) -> str | None:
    """Resolve optional images at any page depth."""
    if element and element.get("src"):
        return urljoin(page_url, str(element["src"]))
    logger.warning("Optional image missing")
    return None


def book_id(url: str) -> str:
    """Extract a strictly validated public product ID from its path."""
    match = re.fullmatch(r"/catalogue/([^/]+)/index\.html", urlsplit(url).path)
    if not match or not BOOK_ID.fullmatch(match[1]):
        raise UpstreamParseError()
    return match[1]


def parse_listing(
    html: str, page_url: str, category: str
) -> tuple[tuple[BookSummary, ...], str | None]:
    """Parse cards, skip isolated malformed cards, and reject unusable pages."""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for card in soup.select("article.product_pod"):
        try:
            anchor = card.select_one("h3 a[href]")
            if not anchor or not str(anchor.get("title", "")).strip():
                raise UpstreamParseError()
            url = urljoin(page_url, str(anchor["href"]))
            books.append(
                BookSummary(
                    id=book_id(url),
                    title=str(anchor["title"]).strip(),
                    price=price(card.select_one("p.price_color")),
                    rating=rating(card.select_one("p.star-rating")),
                    availability=availability(text(card.select_one("p.availability"))),
                    category=category,
                    image_url=image_url(card.select_one("div.image_container img"), page_url),
                    product_url=url,
                )
            )
        except UpstreamParseError:
            logger.warning("Skipped malformed product card")
    if not books:
        raise UpstreamParseError()
    next_link = soup.select_one("li.next a[href]")
    return tuple(books), urljoin(page_url, str(next_link["href"])) if next_link else None


def parse_detail(html: str, page_url: str) -> BookDetail:
    """Read a detail page, tolerating missing non-critical metadata."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("div.product_main")
    if not main or not text(main.select_one("h1")):
        raise UpstreamParseError()
    crumbs = soup.select("ul.breadcrumb li")
    if len(crumbs) < 4 or not text(crumbs[2]):
        raise UpstreamParseError()
    raw_stock = text(main.select_one("p.availability"))
    stock = re.search(r"\((\d+)\s+available\)", raw_stock)
    heading = soup.select_one("#product_description")
    description = text(heading.find_next_sibling("p")) if heading else None
    upc = None
    for row in soup.select("table.table-striped tr"):
        if text(row.find("th")) == "UPC":
            upc = text(row.find("td")) or None
    for label, value in (("description", description), ("stock", stock), ("UPC", upc)):
        if value is None:
            logger.warning("Optional %s missing", label)
    return BookDetail(
        id=book_id(page_url),
        title=text(main.select_one("h1")),
        price=price(main.select_one("p.price_color")),
        rating=rating(main.select_one("p.star-rating")),
        availability=availability(raw_stock),
        category=text(crumbs[2]),
        stock_count=int(stock[1]) if stock else None,
        upc=upc,
        description=description or None,
        image_url=image_url(soup.select_one("div.item.active img"), page_url),
        product_url=page_url,
    )

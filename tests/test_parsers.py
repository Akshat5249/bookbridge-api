"""Fixture-based tests of real URL depths and optional/critical fields."""

from decimal import Decimal
from pathlib import Path

import pytest

from src.exceptions import UpstreamParseError
from src.parsers.books import parse_detail, parse_listing
from src.parsers.categories import parse_categories

SITE = Path(__file__).parent / "fixtures/site"
BASE = "https://books.toscrape.com"
GOLDEN = "a-light-in-the-attic_1000"


def fixture(path: str) -> str:
    return (SITE / path).read_text(encoding="utf-8")


def test_category_links_and_pagination() -> None:
    links = parse_categories(fixture("index.html"), BASE + "/")
    assert len(links) == 40
    assert links[1].category.slug == "science-fiction"
    assert all(link.category.slug != "books" for link in links)
    url = BASE + "/catalogue/category/books/poetry_23/index.html"
    books, next_url = parse_listing(
        fixture("catalogue/category/books/poetry_23/index.html"), url, "Poetry"
    )
    assert len(books) == 20
    assert books[0].title == "A Light in the Attic"
    assert books[0].price == Decimal("51.77")
    assert books[0].rating == 3
    assert books[0].product_url == BASE + f"/catalogue/{GOLDEN}/index.html"
    assert books[0].image_url == BASE + "/media/cache/demo.jpg"
    assert books[2].availability == "out_of_stock"
    assert next_url == url.replace("index.html", "page-2.html")
    tail, following = parse_listing(
        fixture("catalogue/category/books/poetry_23/page-2.html"), next_url, "Poetry"
    )
    assert len(tail) == 1 and following is None


def test_detail_and_missing_optional() -> None:
    url = BASE + f"/catalogue/{GOLDEN}/index.html"
    html = fixture(f"catalogue/{GOLDEN}/index.html")
    book = parse_detail(html, url)
    assert (book.upc, book.stock_count, book.category) == ("a897fe39b1053632", 22, "Poetry")
    assert book.description == "A public demo description."
    assert book.image_url == BASE + "/media/cache/demo.jpg"
    assert parse_detail(html.replace("£", "Â£"), url).price == book.price
    no_desc = parse_detail(
        fixture("catalogue/sample-book-1_999/index.html"),
        BASE + "/catalogue/sample-book-1_999/index.html",
    )
    assert no_desc.description is None
    assert "&" in no_desc.title and "’" in no_desc.title
    stripped = (
        html.replace('src="../../media/cache/demo.jpg"', "")
        .replace("(22 available)", "")
        .replace("<th>UPC</th>", "<th>Other</th>")
    )
    optional = parse_detail(stripped, url)
    assert optional.image_url is optional.stock_count is optional.upc is None


@pytest.mark.parametrize("html", ["", "<h1>Maintenance</h1>"])
def test_unusable(html: str) -> None:
    with pytest.raises(UpstreamParseError):
        parse_listing(html, BASE + "/", "Poetry")
    with pytest.raises(UpstreamParseError):
        parse_detail(html, BASE + f"/catalogue/{GOLDEN}/index.html")
    with pytest.raises(UpstreamParseError):
        parse_categories(html, BASE + "/")


@pytest.mark.parametrize(
    "before,after",
    [
        ('title="A Light in the Attic"', 'title=""'),
        ("£51.77", "bad"),
        ("star-rating Three", "star-rating Six"),
        ("a-light-in-the-attic_1000", "invalid"),
    ],
)
def test_bad_card_skipped(before: str, after: str) -> None:
    html = fixture("index.html")
    books, _ = parse_listing(html.replace(before, after, 1), BASE + "/", "Poetry")
    assert len(books) == 19


def test_home_and_catalogue_relative_urls() -> None:
    html = fixture("index.html")
    home, _ = parse_listing(html, BASE + "/index.html", "Poetry")
    page, _ = parse_listing(
        html.replace('href="catalogue/', 'href="'), BASE + "/catalogue/page-2.html", "Poetry"
    )
    assert home[0].product_url == page[0].product_url
    assert {book.rating for book in home} == {1, 2, 3, 4, 5}


def test_saved_public_markup() -> None:
    """Regression-check real pages saved once; no test performs network I/O."""
    root = SITE.parent / "reference"
    home = (root / "home.html").read_text(encoding="utf-8")
    categories = parse_categories(home, BASE + "/")
    assert len(categories) == 50
    assert categories[0].category.slug == "travel"
    listed, _ = parse_listing(home, BASE + "/", "Unassigned")
    assert len(listed) == 20
    assert listed[0].title == "A Light in the Attic"
    assert listed[0].price == Decimal("51.77")
    for name, folder, count in [
        ("Poetry", "poetry_23", 19),
        ("Science Fiction", "science-fiction_16", 16),
    ]:
        file = "poetry.html" if name == "Poetry" else "science-fiction.html"
        books, next_url = parse_listing(
            (root / file).read_text(encoding="utf-8"),
            BASE + f"/catalogue/category/books/{folder}/index.html",
            name,
        )
        assert len(books) == count and next_url is None
        assert all(book.category == name for book in books)

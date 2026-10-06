# UPSTREAM SITE NOTES — BookBridge API

*Reverse-engineering findings: URL map, markup, quirks and fixture templates*

## Purpose

This document records how the public Books to Scrape website is structured, so that the implementation, parser and test fixtures match the real markup. It is the 'reverse-engineering' evidence for the assignment. Items marked (verify) should be confirmed against saved fixtures; if a fixture contradicts this document, the fixture wins and the discrepancy goes into REVERSE_ENGINEERING_NOTES.md.

## Target and Terms

- Base URL: `https://books.toscrape.com/`. A public sandbox site published for scraping practice: static HTML, no login, fictional catalogue, no user data.
- About 1,000 books in about 50 categories (excluding the top-level 'Books' node). All prices are in GBP.
- No hidden JSON/XHR endpoints were found while inspecting page behaviour (verify in browser dev tools). The HTML itself is the only machine-readable contract, which is exactly the fragility the limitations note describes.
- Only GET requests to ordinary public pages are allowed. Never submit the 'Add to basket' form or any other form.

## URL Map

| Resource | Pattern | Notes |
| --- | --- | --- |
| Home | `/` or `/index.html` | First page of all books plus the category sidebar. |
| Category list | Sidebar on the home page | Selector `div.side_categories ul li ul li a`. Skip the top-level 'Books' link (`books_1`). |
| Category page | `/catalogue/category/books/{folder}/index.html` | `{folder}` is `{slug}_{number}`, e.g. `poetry_23`, `science-fiction_16`. |
| Category pagination | `/catalogue/category/books/{folder}/page-{n}.html` | Only exists when the category has more than 20 books. Follow `li.next a`. |
| Book detail | `/catalogue/{slug}_{n}/index.html` | Public book id = `{slug}_{n}`, e.g. `a-light-in-the-attic_1000`. |
| All-books listing | `/catalogue/page-{n}.html` | 20 per page, about 50 pages. NOT used for the index (see doc 10, D2). |
| Images | `/media/cache/xx/yy/{hash}.jpg` | Always resolve with `urljoin(page_url, src)`. |
| robots.txt | `/robots.txt` | Fetch once; a 404 means no restrictions. Honour any Disallow. |

## Relative URL Behaviour

Link depth differs per page type, so every href and src must be resolved with `urllib.parse.urljoin(current_page_url, value)`. Never concatenate strings.

| Page | Example href / src | Resolves against |
| --- | --- | --- |
| Home | `catalogue/a-light-in-the-attic_1000/index.html` | `https://books.toscrape.com/index.html` |
| All-books page 2 | `a-light-in-the-attic_1000/index.html` | `https://books.toscrape.com/catalogue/page-2.html` |
| Category page | `../../../a-light-in-the-attic_1000/index.html` | `.../catalogue/category/books/poetry_23/index.html` |
| Category image | `../../../../media/cache/2c/da/....jpg` | same category page URL |
| Detail image | `../../media/cache/2c/da/....jpg` | `.../catalogue/{id}/index.html` |

## Listing and Category Page Selectors

| Field | Selector / rule | Transformation |
| --- | --- | --- |
| Product card | `article.product_pod` | One per book. |
| id | `h3 a[href]` | Regex `([^/]+_\d+)/index\.html$` on the href. |
| title | `h3 a[title]` attribute | Visible link text is truncated with '...'; always use the `title` attribute. |
| price | `p.price_color` | '£51.77' -> Decimal 51.77, currency GBP. |
| rating | `p.star-rating` class list | Second class token One..Five -> 1..5. |
| availability | `p.availability` text | 'In stock' -> in_stock; 'Out of stock' -> out_of_stock; else unknown. |
| image_url | `div.image_container img[src]` | `urljoin`. |
| product_url | `h3 a[href]` | `urljoin`. |
| result count (optional) | `form.form-horizontal strong` | First `strong` = number of results (verify). Use only as a sanity check. |
| next page | `li.next a[href]` | `urljoin`; absent on the last page. |

## Detail Page Selectors

| Field | Selector / rule | Transformation |
| --- | --- | --- |
| title | `div.product_main h1` | Text. |
| price | `div.product_main p.price_color` | As above. |
| rating | `div.product_main p.star-rating` | As above. |
| availability + stock_count | `div.product_main p.availability` | 'In stock (22 available)' -> in_stock, 22 via regex `\((\d+)\s+available\)`. |
| category | `ul.breadcrumb li` third item | Home > Books > **Poetry** > Title. |
| description | `#product_description` -> next sibling `p` | Element is absent for some books -> `null`. |
| upc | `table.table-striped` row whose `th` is 'UPC' | Text of the `td`. |
| image_url | `div.item.active img[src]` | `urljoin`. |
| Other table rows | Product Type, Price (excl./incl. tax), Tax, Availability, Number of reviews | Not exposed in v1. |

## Quirks and Edge Cases

- Encoding: pages are UTF-8 but the charset may not be declared. Decode `response.content` explicitly as UTF-8. The price parser must also tolerate the mojibake form 'Â£' by extracting the number with a regex such as `(\d+(?:\.\d+)?)` and mapping a trailing/leading '£' or 'Â£' to GBP.
- Category anchor text contains surrounding whitespace/newlines: strip it.
- Public category slug = lowercase name with runs of non-alphanumerics replaced by '-': 'Science Fiction' -> `science-fiction`, 'Sports and Games' -> `sports-and-games`, 'Add a comment' -> `add-a-comment`. The slug is mapped to the upstream folder using the parsed home page, never guessed.
- Every book belongs to exactly one category. De-duplicate by id anyway.
- Natural catalogue order is descending numeric id (1000 first) (verify). This defines the default sort.
- Some books have no description, some titles contain apostrophes, ampersands or non-ASCII characters; fixtures must cover these.
- Pages are static; no JavaScript is needed or executed. Do not use a headless browser.

## Fixture Templates

If the network is unavailable, hand-write fixtures from these templates. Keep the same class names and nesting; vary the data.

### Category page card

```
<article class="product_pod">
  <div class="image_container">
    <a href="../../../a-light-in-the-attic_1000/index.html">
      <img src="../../../../media/cache/2c/da/2cdad67c.jpg"
           alt="A Light in the Attic" class="thumbnail"></a>
  </div>
  <p class="star-rating Three"><i class="icon-star"></i></p>
  <h3><a href="../../../a-light-in-the-attic_1000/index.html"
         title="A Light in the Attic">A Light in the ...</a></h3>
  <div class="product_price">
    <p class="price_color">£51.77</p>
    <p class="instock availability"><i class="icon-ok"></i> In stock</p>
  </div>
</article>
<li class="next"><a href="page-2.html">next</a></li>
```

### Detail page core

```
<ul class="breadcrumb"><li><a href="../../index.html">Home</a></li>
  <li><a href="../category/books_1/index.html">Books</a></li>
  <li><a href="../category/books/poetry_23/index.html">Poetry</a></li>
  <li class="active">A Light in the Attic</li></ul>
<div class="item active"><img src="../../media/cache/fe/72/fe72.jpg"></div>
<div class="product_main"><h1>A Light in the Attic</h1>
  <p class="price_color">£51.77</p>
  <p class="instock availability">In stock (22 available)</p>
  <p class="star-rating Three"></p></div>
<div id="product_description" class="sub-header"><h2>Product Description</h2></div>
<p>Description text ...</p>
<table class="table table-striped">
  <tr><th>UPC</th><td>a897fe39b1053632</td></tr>
  <tr><th>Product Type</th><td>Books</td></tr>
  <tr><th>Price (excl. tax)</th><td>£51.77</td></tr>
  <tr><th>Availability</th><td>In stock (22 available)</td></tr>
</table>
```

### Home page sidebar

```
<div class="side_categories"><ul class="nav nav-list">
  <li><a href="catalogue/category/books_1/index.html">Books</a>
    <ul>
      <li><a href="catalogue/category/books/poetry_23/index.html">
          Poetry </a></li>
      <li><a href="catalogue/category/books/science-fiction_16/index.html">
          Science Fiction </a></li>
    </ul></li></ul></div>
```

## Fixture Mini-Site Coverage

Store fixtures under `tests/fixtures/site/` mirroring the real URL layout so the same directory can back both respx-mocked pytest runs and the local fake upstream used by the evaluator.

- Home page with at least four categories, including a multi-word name and the top-level 'Books' link.
- At least one category spanning two pages (page 1 with `li.next`, page 2 without) and one single-page category.
- At least 10 books in total across categories, covering: rating 1..5, one price exactly 10.00 and one exactly 40.00 (inclusive boundary tests), one 'Out of stock', one title with an apostrophe or ampersand, and ids in descending order.
- Detail pages for several books, including the golden record `a-light-in-the-attic_1000` (price 51.77, rating 3, Poetry, UPC a897fe39b1053632, 22 available) and one book with no description.
- A deliberately broken page (valid HTTP 200, no product cards) for the parse-failure test.

## Dev-Time Verification Budget

If network access exists, Codex may fetch at most about 10 public pages once (home, robots.txt, one single-page category, one two-page category, three detail pages including one without a description) using the project User-Agent and a delay between requests, then save them as fixtures. Never run a full crawl during development or tests. If a live check fails or is blocked, stop, record it, and continue with hand-written fixtures.

---
BookBridge API • Razorpay Reverse-Engineering Assignment

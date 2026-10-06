# Reverse-engineering notes

Books to Scrape is the chosen public, unauthenticated sandbox. The implementation
started from all twelve supplied specs, with synthetic fixtures preserving their
selector templates. On 7 October 2026 the complete live evaluator passed all 36
live scenarios through the actual service; the lazy index warmup took about 11.3s.
Three representative public HTML pages were then saved once under
`tests/fixtures/reference/` and are regression-tested offline.

The sidebar exposes 50 categories. The first all-books card is
`a-light-in-the-attic_1000`; Poetry contains 19 books and Science Fiction 16.
An assumed Science Fiction `page-2.html` returned 404, so fixture capture stopped.
This reinforced following actual `li.next a[href]` links rather than guessing page
counts. The synthetic mini-site deliberately includes a two-page category and
60 books across 40 categories to exercise all evaluator requirements offline.

| Page | URL / discovery | Selectors |
| --- | --- | --- |
| Home | `/` | `div.side_categories ul li ul li a` |
| Category | `/catalogue/category/books/{folder}/index.html` from sidebar | `article.product_pod`, `li.next a[href]` |
| Category continuation | Resolved next link (usually `page-N.html`) | Same cards |
| Book detail | `/catalogue/{validated-id}/index.html` | `div.product_main`, breadcrumb, product table |
| Images | Resolved relative `src` | `div.image_container img`, `div.item.active img` |
| robots | `/robots.txt` once per process | Python RobotFileParser; live response was 404 |

Listing titles come from `h3 a[title]`, since visible link text is truncated.
Prices come from `p.price_color`: explicitly decode UTF-8, accept the documented
`Â£` fallback and parse GBP into Decimal. Ratings are the One–Five classes on
`p.star-rating`. Availability comes from `p.availability`. Listings lack category,
so the index assigns the enclosing sidebar category. IDs come from detail URL
paths, and summaries sort by descending numeric suffix.

Details use `div.product_main h1`, its price/rating/availability, the third
breadcrumb item, the `UPC` row in `table.table-striped`, and the paragraph after
`#product_description`. Stock is extracted from `(N available)`. Missing images,
UPC, description or stock become null with warnings. Unusable critical markup
produces controlled 502; isolated malformed cards are skipped with a warning.

Every relative link uses `urljoin(current_page_url, href)`, since home, category
and detail paths have different depths. Public category slugs are derived from
names and mapped to parsed folders. The client validates origin, rejects unsafe
redirects and follows at most three. Pagination is confined to its category folder
and detects loops. User input supplies only a validated book ID; category input
never constructs an upstream URL.

No JSON/XHR endpoint is used. HTML links and selectors are the integration
contract. Browser DevTools network inspection was not performed, so this report
does not claim to prove that no hidden JSON endpoint exists. No JavaScript,
browser automation, forms, login, private data or privileged endpoints are used.

# Limitations and long-term fix

BookBridge is an educational, read-only adapter over public Books to Scrape HTML.
The sandbox catalogue is fictional and does not represent purchasing or inventory guarantees.

- It depends on HTML presentation rather than a documented machine contract.
- The first catalogue request builds an index from about 70 pages, adding latency.
- Cached and stale-if-error responses have no strong freshness guarantee; each process
  keeps its own index, so multiple workers duplicate crawling and memory.
- Displayed prices, ratings and availability may omit underlying domain information.
- Source policy, robots rules or access restrictions may change.

Markup, URL and pagination changes can silently break parsing while the website still
works for people. Fixture tests, isolated parsers, bounded retries, conservative pacing
and controlled 502/504 errors reduce the impact but cannot eliminate this fragility.
An isolated malformed listing card is skipped with a warning, so results can be incomplete.
A failed refresh retains the prior snapshot and waits 30 seconds before trying again.

The appropriate production fix is an official documented API or an authorized data feed.
If none exists, seek an owner-approved partnership with an agreed contract,
authentication, quotas, versioning, availability SLAs and change notifications.

Restrictions are boundaries: never bypass CAPTCHA, rotate proxies, impersonate users,
harvest cookies or credentials, or evade robots rules and rate limits.

Migration:

1. Keep the normalized consumer contract.
2. Obtain an authorized API or feed with clear usage terms.
3. Implement a provider adapter behind the existing service interface.
4. Run contract tests comparing both providers.
5. Switch traffic and retire HTML scraping.

# Implementation plan

All twelve specification files were read before implementation. Preserve them and
`.env.example`. Implement fixtures and pure parsers first, then settings/cache/client,
index/services, API and errors, standalone evaluator, deployment files and docs.
Run the tests after each layer and the complete offline evaluator before live checks.

Files: `src/{api,clients,parsers,services,schemas}`, settings, cache, exceptions and
app factory; fixture mini-site and parser/client/cache/service/API/error tests;
`scripts/{fake_upstream,test_api}.py`; pinned requirements, pyproject, Docker,
Makefile, CI, README, limitations and reverse-engineering notes.

Resolved ambiguities:
- Doc 10 expands the abbreviated detail example in doc 04 into the full SPEC schema.
- Both price bounds are nonnegative; malformed book IDs return 404 per D3/D8.
- The master prompt supersedes doc 08. Category pages, not all-books pages, build
  the index; details are fetched only on demand.
- JSON prices are numbers (e.g. 10.0); JSON cannot guarantee retained trailing zeros.
  Internal prices are Decimal quantized to two places.
- Expand the synthetic mini-site minimum to 60 books/40 categories so the unchanged
  live evaluator checks (50-item page and 40 categories) also work entirely offline.
- Robots 404/network errors mean allowed, as D10 specifies; access restrictions
  (403/429), other HTTP errors and unsafe redirects fail closed without evasion.
- Failed index refresh retains the prior immutable snapshot; serialize refreshes
  and briefly back off failed refreshes to avoid repeated crawls during an outage.
- Upstream links must stay within the configured origin and public catalogue URL
  patterns, even when supplied by HTML. The client never trusts environment proxies.
- No delegated agents: neither the master prompt nor repo instructions request them.

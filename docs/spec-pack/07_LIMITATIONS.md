**Limitations ****&**** Long-Term Fix**

*Required reverse-engineering limitations note*

# Primary Limitation

The integration depends on a presentation layer rather than a documented machine contract. HTML structure, CSS classes, URL patterns, pagination and displayed fields can change without notice and break parsing while the website still works for humans.

# Other Limitations

Search can require reading multiple catalogue pages and is less efficient than a native indexed API.

Uncached requests inherit upstream latency/outages.

Displayed information may not expose all underlying domain data.

Source policies or request restrictions can change.

Strong freshness, uptime and backwards compatibility cannot be guaranteed.

# Mitigations

Parser isolation and fixture tests.

Timeouts and bounded retries.

Short TTL caching and conservative request volume.

Controlled 502/504 responses.

Normalized schemas shield consumers from markup details.

# Appropriate Long-Term Fix

For production, use an official documented API or authorized data feed from the source owner. If none exists, seek permission/partnership and agree on a stable machine-readable interface, authentication, quotas, versioning, availability expectations and change notifications.

# Do Not Circumvent

Do not react to restrictions by bypassing CAPTCHA, rotating proxies, impersonating users, harvesting credentials/cookies, defeating rate limits or accessing private endpoints. Treat restrictions as a boundary and move to an authorized integration path.

# Migration Path

Define the normalized consumer contract.

Obtain an authorized upstream API/feed.

Implement a provider adapter behind the same service interface.

Run contract tests during migration.

Switch traffic and retire HTML scraping.


---
BookBridge API • Razorpay Reverse-Engineering Assignment

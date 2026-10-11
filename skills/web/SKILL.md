---
name: web
description: Search the web and read pages, for current events, facts, prices and documentation.
keywords: [search, google, look up, lookup, web, internet, online, news, latest, website, webpage, article, url, link, browse, source]
---
1. Call `search` with a short query (3-6 words).
2. Call `read_url` on the most relevant result. Pass `query` with what you need, so you get only the matching paragraphs. Read a second page only if the first one doesn't answer.
3. If `read_url` says BLOCKED, NOT_FOUND, TIMEOUT or JS_REQUIRED, try the next result.
4. Answer in a few sentences and name the source.

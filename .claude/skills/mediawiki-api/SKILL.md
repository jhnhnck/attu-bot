---
name: mediawiki-api
description: mediawiki action api + mwparserfromhell reference card for AttuBot's wiki layer. trigger when editing or creating files under doom_bot/wiki/, doom_bot/ingestor/pipelines/wiki.py, or doom_bot/commands/wiki.py; when any file imports mwparserfromhell or hits api.php / rest.php; when writing or reviewing wiki search, page fetch, page edit, login or csrf token flow, edit-conflict handling, recent-changes ingestion, allpages pagination, or section-split / wikitext-traversal logic.
---

# mediawiki api reference

scope: pinned to **mediawiki 1.44.5** (vanilla self-host, php 8.4, mariadb) at `https://attuproject.org`, verified via `siteinfo` on 2026-05-04. wiki url comes from `[auth.wiki].endpoint` in `assets/attu-bot.toml`. if the wiki upgrades majorly (e.g. 1.45+, fandom/ucp migration, or mediawiki 2.x), re-verify token flow, `formatversion=2` shape, and rest.php availability before trusting this file.

mwparserfromhell version follows the lockfile; the traversal model has been stable since 0.6.x but `get_sections` / `filter_templates` defaults still trip up llms regularly. trust this file and the existing repo code over training-data recall.

## the two apis (and why this repo uses both)

| surface | mount | shape | use for |
|---|---|---|---|
| **action api** | `/api.php` | sprawling, idiosyncratic, fully featured | auth, page reads, edits, allpages, recentchanges, siteinfo, admin (block) |
| **rest api** | `/rest.php/v1/...` | small, modern, partial replacement | full-text and title search only; everything else is incomplete or absent |

the rest api is **not** a drop-in replacement; it covers a curated subset (search, page get, page history) and is missing edits, login, and most query modules. on some wikis it is disabled outright. default to the action api unless a specific endpoint is known to exist on rest.php; on this wiki only `/rest.php/v1/search/page` and `/rest.php/v1/search/title` are in active use (see `doom_bot/wiki/search.py`).

`WikiClient.__init__` already exposes both bases:

```python
self._action = '/api.php'
self._rest = '/rest.php/v1'
```

do not invent `/w/api.php` or `/api/rest_v1/` paths; both are wikipedia/wikimedia-cluster mounts and 404 here.

## action api basics

every action api call:

```
GET  api.php?action=<name>&format=json&formatversion=2&...
POST api.php  (form-encoded body with same keys)
```

mandatory params on every read or write:

- `format=json` - the only format this codebase parses; `xml` and `php` exist but are unused.
- `formatversion=2` - **always pin this**. v1 and v2 response shapes differ enough to silently break the pydantic models in `doom_bot/wiki/models.py`. v1 returns `query.pages` as a dict keyed by page id; v2 returns it as a list. v1 omits missing fields entirely; v2 normalizes more keys. mixing versions across calls is the fastest way to introduce silent ingestion bugs.

`doom_bot/wiki/auth.py:23-30` (`get_csrf`) currently omits `formatversion`; this happens to work because the `tokens` shape is identical across versions, but new call sites should pin v2 by default.

## auth flow (as actually implemented)

this repo uses **bot passwords with `action=login`**, not `clientlogin`. credentials come from `Special:BotPasswords` and are stored in `assets/attu-bot.toml` as `[auth.wiki].user` / `.key` (e.g. `DoomBot@DoomBot`).

implemented in `doom_bot/wiki/auth.py`; the dance is:

1. **fetch login token**
   ```
   GET api.php?action=query&meta=tokens&type=login&format=json
   → query.tokens.logintoken
   ```

2. **post credentials with the login token**
   ```
   POST api.php
     action=login
     lgname=<user>
     lgpassword=<key>
     lgtoken=<logintoken>
     format=json
   → login.result == 'Success'
   ```
   the session cookie set by this response is what authenticates subsequent requests; `httpx.AsyncClient` carries it automatically because `WikiClient` reuses one client across all four sub-apis (`auth`, `pages`, `search`, `admin`).

3. **fetch a csrf token for any write**
   ```
   GET api.php?action=query&meta=tokens&format=json
   → query.tokens.csrftoken
   ```
   `type` defaults to `csrf` when omitted; that is what `AuthApi.get_csrf` relies on. one csrf token is valid for many edits in the same session, but the repo currently fetches a fresh one per write (cheap, simpler, no expiry tracking).

4. **submit the write with `token=<csrf>`** in the post body. the token must be the **last field** the server reads; if the request is truncated mid-flight, the token is missing and the write is rejected. http form encoding does not guarantee order on its own - in practice the python `dict` insertion order is preserved by httpx, and the existing `pages.edit` / `admin.block` payloads put `token` last. preserve that ordering when adding new write calls.

footguns specific to this repo:

- `WikiClient.authenticate(user, key)` is only called from `doom_bot/commands/wiki.py:269` (`/wiki block`); there is no standing logged-in session. any new write path must call `await wiki.authenticate(...)` first or `get_csrf()` will return the anonymous-user `+\\` token, which mediawiki will reject for non-anon writes.
- session cookies live on the shared `httpx.AsyncClient`. if you ever rebuild the client mid-process, you lose the session and silently drop to anon.
- `clientlogin` (mw 1.27+) is the newer interactive flow with multi-step responses (captcha, 2fa). don't switch to it without a reason; bot passwords + `action=login` works fine on vanilla mw 1.44.

## read endpoints

three distinct shapes; pick by what you need.

| call | use when | response root |
|---|---|---|
| `action=parse&page=X&prop=wikitext&formatversion=2` | you need just the raw wikitext (no metadata, no rev id). `pages.get` uses this. | `parse.wikitext` (string in v2) |
| `action=query&titles=X&prop=revisions&rvprop=ids\|timestamp\|content&rvslots=main&formatversion=2` | you need wikitext **plus** rev id and timestamp for staleness checks. `pages.get_with_revision` uses this. | `query.pages[0].revisions[0].slots.main.content` |
| `action=query&titles=X&prop=extracts\|pageimages&exintro=1&explaintext=1&pithumbsize=500&formatversion=2` | you need a plain-text intro extract and thumbnail for an embed. `pages.get_summary` uses this. | `query.pages[0]` → `PageSummary.model_validate(...)` |

**`rvslots=main` is mandatory** when requesting `rvprop=content` on modern mediawiki. omitting it works (returns content in the legacy backwards-compat shape) but emits a deprecation warning; in a future mw release it becomes a hard error. the pipeline parses `revisions[0].slots.main.content`, which only exists when `rvslots=main` is sent.

generators (e.g. `generator=random`, `generator=allpages`) compose with `prop=...` to fetch metadata for a generated set of pages in one round trip; `pages.get_random_summary` uses `generator=random&grnnamespace=<n>` for /wiki random.

**namespace numbers** that matter on this wiki: `0` = main (default for ingestion and `/wiki random`); other namespaces (Project, Category, Template, etc.) are ingested only if explicitly listed in `config.chat_runtime.wiki_namespaces`.

## search endpoints

this repo uses three search variants; know which is which.

### rest api `/rest.php/v1/search/page` (full-text)

what `SearchApi.search` calls. used by `/wiki lookup` and `WikiLookupView` for the body-search results.

```
GET rest.php/v1/search/page?q=<query>&limit=<n>
→ { "pages": [ { "id", "key", "title", "excerpt", "matched_title", "description", "thumbnail" }, ... ] }
```

`excerpt` includes `<span class="searchmatch">...</span>` highlighting markup; strip or render as appropriate. the api does not always respect `limit` exactly, so the repo truncates the list manually after parsing (`search.py:35-37`).

### rest api `/rest.php/v1/search/title` (title-only)

what `SearchApi.search_title` calls. used by `/wiki lookup` to bias the first result toward an exact title match before mixing in body hits.

same response shape as `/search/page`. cheaper and more useful for autocomplete-style flows.

### action api `list=search` (full-text, action variant)

equivalent to rest `search/page` but on the action surface. **not currently used** in this repo, but worth knowing about: it returns more metadata via `srprop` (size, wordcount, sectiontitle, snippet, etc.) and supports namespace filters via `srnamespace`.

```
GET api.php?action=query&list=search&srsearch=<q>&srlimit=10&srprop=snippet|sectiontitle&format=json&formatversion=2
→ query.search[*]
```

### action api `list=prefixsearch` (autocomplete)

```
GET api.php?action=query&list=prefixsearch&pssearch=<q>&pslimit=10&format=json&formatversion=2
→ query.prefixsearch[*]
```

### action api `action=opensearch` (legacy autocomplete)

returns a deliberately awkward four-element array, **not** the standard envelope:

```json
[
  "<query string>",
  ["Title 1", "Title 2", ...],
  ["desc 1", "desc 2", ...],
  ["url 1", "url 2", ...]
]
```

four parallel arrays of equal length; index `i` is one result. parse defensively or you will silently truncate. prefer `prefixsearch` over `opensearch` for new code; opensearch exists for browser-bar integration, not for application code.

## editing pages

implemented in `doom_bot/wiki/pages.py:41-58` (`PagesApi.edit`). minimum viable write:

```
POST api.php
  action=edit
  title=<page>
  text=<full new wikitext>
  summary=<edit summary>
  bot=1                # mark as bot edit; suppresses RC by default for users with the botflag
  minor=1              # optional; flags as a minor edit
  format=json
  formatversion=2
  token=<csrf>         # always last; see auth flow note above
```

variants:

- `text=<full text>` - replaces the page entirely. what this repo does.
- `appendtext=<chunk>` - appends to the end. use for append-only logs (not currently used here).
- `prependtext=<chunk>` - prepends to the top.
- `section=<n>` - target a specific section by index (0 = lead). pair with `text=` to replace just that section. `section=new` adds a new section; pair with `sectiontitle=`.

response on success: `edit.result == 'Success'` plus the new `newrevid`, `oldrevid`, `newtimestamp`. on failure: an `error` object with a `code`.

**conflict-detection params - currently missing from this repo's edit path.** if you add concurrent-write logic, include them:

- `basetimestamp=<rev timestamp>` - the timestamp of the revision the edit is based on. obtained from the prior `get_with_revision` call.
- `starttimestamp=<now>` - the timestamp at which editing began.
- `baserevid=<revid>` - mw 1.35+; alternative to `basetimestamp`, more precise. obtained from the prior `get_with_revision` call.

mediawiki uses these to detect that someone else edited the page between your read and your write. without them, last-writer-wins; you will silently overwrite a concurrent edit. `pages.get_with_revision` already returns `(wikitext, revid, rev_timestamp, categories)` - the second and third values are exactly what these params want.

## edit conflicts

on conflict the api returns http 200 with:

```json
{ "error": { "code": "editconflict", "info": "Edit conflict." } }
```

recommended retry (one round, then bail):

1. re-fetch wikitext via `pages.get_with_revision` to get the new revid and timestamp.
2. reapply your diff onto the new content. if the diff cannot be reapplied cleanly (text the diff depended on is gone), abort and surface the error.
3. retry `edit` with the new `basetimestamp` / `baserevid`. on a second `editconflict`, give up and report; do not loop.

other write-path errors worth handling explicitly:

- `code=protectedpage` - page is protected; no retry will help. surface to the caller.
- `code=blocked` - the bot account is blocked. surface and do not retry.
- `code=ratelimited` - per-user write throttling. sleep `Retry-After` seconds and retry once.
- `code=badtoken` / `code=notoken` - csrf token expired or missing; refetch a fresh csrf and retry once.
- `code=assertbotfailed` / `code=assertuserfailed` - session lost. re-authenticate and retry once.

## rate limits and maxlag

- **`maxlag=5`** on every read; cheap insurance. on a `maxlag` error (http 200 with `error.code='maxlag'`) sleep the `Retry-After` seconds (default 5) and retry once. don't busy-loop. not currently passed by this repo's read calls; safe to add.
- writes ignore `maxlag` server-side but obey the per-user write throttle, surfaced as `code=ratelimited`.
- the admin `block` action has its own throttle and is the most rate-limit-sensitive call in this repo. `admin.block` retries up to `max_retries=3` with a flat `asyncio.sleep(3)` between attempts (`doom_bot/wiki/admin.py:44-54`); this is intentional and survives both transient http failures and short-lived rate limits. do not lower the retry count or remove the sleep.
- for `assert=user` / `assert=bot` on write traffic: not currently used here. add it to a new write path if you want to fail loudly on session loss instead of silently writing as anon.

## mwparserfromhell traversal

import once; parse once per page; reuse the result. `mwparserfromhell.parse(text)` returns a `Wikicode`.

### the section split this repo actually uses

from `doom_bot/ingestor/pipelines/wiki.py:153-168`:

```python
parsed = mwparserfromhell.parse(wikitext)
for section in parsed.get_sections(include_lead=True, flat=True):
    headings = section.filter_headings()
    title = headings[0].title.strip() if headings else ''
    text = section.strip_code().strip()
    if text:
        sections.append((title, text))
```

what each flag does and why these settings are right for the rag corpus:

- `include_lead=True` - include the content before the first `==` heading as a section. omitting it loses the page's intro entirely. the lead has no heading object, so `filter_headings()` returns `[]` and `title` falls through to `''`; the pipeline labels it `'(intro)'` downstream.
- `flat=True` - return one section per heading, **without** its subsections nested inside. `flat=False` would return each section as a tree containing all its children, which means the same text appears in multiple sections (the parent and each child) and the embedding corpus double-counts. always pass `flat=True` for ingestion.
- `strip_code()` - render to plain text: drops templates, reduces links to display text, strips markup. fast and deterministic; loses structure (lists become flat lines, tables become whitespace). acceptable for embedding; not acceptable if you ever need to round-trip to wikitext.

do not switch to `get_sections(flat=False)` or `include_lead=False` without also changing the ingestor's dedup logic in `_ingest_page`; the section `source_id` keying assumes one entry per heading.

### filter_templates and recursion

`Wikicode.filter_templates(recursive=True)` is the **default**; it walks all descendants. `recursive=False` only looks at direct children of the wikicode, which means nested templates (very common - infoboxes contain other templates) are silently skipped. for ingestion or any analysis that must visit every template, never pass `recursive=False`.

```python
for template in parsed.filter_templates():
    name = str(template.name).strip().lower()
    if name == 'infobox character':
        for param in template.params:
            ...
```

key shapes:

- `template.name` is itself `Wikicode`, not a string; cast with `str(...)` and `.strip()` before comparing.
- `template.params` is a list of `Parameter`; each has `.name` and `.value`, both `Wikicode`.
- `template.get('field_name').value` returns `Wikicode`, which **may itself contain nested templates** - call `strip_code()` (or recurse) before treating it as text.
- `template.has('field_name')` checks parameter presence without raising.

### other traversal helpers

- `parsed.filter_links()` - all wikilinks (`[[Foo]]`); each has `.title` and `.text`.
- `parsed.filter_external_links()` - bare urls and bracketed externals.
- `parsed.filter_tags()` - html-style tags (`<ref>`, `<gallery>`, etc.); `.tag` is the name.
- `parsed.filter_headings()` - `==`-style headings; `.level` is the depth, `.title` is `Wikicode`.
- `parsed.ifilter(...)` / `parsed.filter(...)` - generic filters; pass `forcetype=Template` etc.
- `parsed.nodes` - raw node list for manual traversal; rarely needed.

`filter_*` methods all accept `recursive=True/False` (default `True`) and a `matches=` predicate. when in doubt: the default is the right answer; only deviate with intent.

### round-trip note

`mwparserfromhell` is round-trip safe: `str(parsed) == original_wikitext` after parse, even if you mutate templates or text in place. `strip_code()` is the lossy escape hatch for embedding; do not use it as the source of truth for an edit you intend to write back to the wiki.

## footguns and common confusions

- `formatversion=1` vs `formatversion=2` shape drift silently breaks `query.pages` (dict in v1, list in v2) and missing-field handling. always pin v2.
- `rvslots=main` is mandatory when reading `rvprop=content`; omitting it triggers a deprecation warning today and will hard-fail in a future mw.
- the rest api at `/rest.php/v1/...` is a partial replacement, not a drop-in. it has no auth, no edits, and limited query coverage. on this wiki only `/search/page` and `/search/title` are in use.
- `/api/rest_v1/...` is a wikimedia-cluster path, not a standard mediawiki mount. on attuproject.org it 404s.
- csrf tokens come from `meta=tokens&type=csrf` (or `type` omitted; defaults to csrf). login tokens come from `meta=tokens&type=login`. they are not interchangeable; using a login token to write returns `code=badtoken`.
- session is carried on the shared `httpx.AsyncClient`; if you instantiate a second client mid-process you lose the session.
- `bot=1` requires the account to have the bot flag; without it, the param is silently ignored and the edit shows up in normal recentchanges.
- `mwparserfromhell.filter_templates(recursive=False)` skips nested templates (infobox-inside-infobox is common). leaving it at the default `True` is almost always correct.
- `Wikicode.get_sections(flat=False)` returns nested wikicode trees and double-counts content under parent-child headings; use `flat=True` for embedding pipelines.
- `template.name` and `template.get('x').value` are `Wikicode`, not strings. `str(...)` plus `.strip()` (or `.strip_code()`) before comparing.
- `action=opensearch` returns a four-element array, not a normal `{query: ...}` envelope. parse defensively.
- the rest search api ignores `limit` slightly; truncate manually after parse (`search.py:36`).
- `pages.edit` here does not pass `basetimestamp` / `baserevid`; concurrent edits will silently last-write-wins. add the params if a new write path needs conflict detection.
- never run live edits or admin actions during testing or research. read-only api calls against a public wiki (e.g. en.wikipedia.org/w/api.php) are fine for verifying response shapes; writes against attuproject.org are not.
- per `docs/agents.md` and `CLAUDE.md`: never trigger discord-side interactions or commit changes without explicit user instruction.

## quick links

- mediawiki action api index: https://www.mediawiki.org/wiki/API:Main_page
- api:edit (conflict params): https://www.mediawiki.org/wiki/API:Edit
- api:login (bot password flow): https://www.mediawiki.org/wiki/API:Login
- api:tokens: https://www.mediawiki.org/wiki/API:Tokens
- api:revisions (`rvslots=main`): https://www.mediawiki.org/wiki/API:Revisions
- api:search variants: https://www.mediawiki.org/wiki/API:Search
- maxlag manual: https://www.mediawiki.org/wiki/Manual:Maxlag_parameter
- mediawiki rest api: https://www.mediawiki.org/wiki/API:REST_API
- mwparserfromhell docs: https://mwparserfromhell.readthedocs.io/
- repo files (authoritative shapes):
  - `doom_bot/wiki/client.py` - facade, base urls, user-agent
  - `doom_bot/wiki/auth.py` - login + csrf flow
  - `doom_bot/wiki/pages.py` - parse / revisions / extracts / allpages / recentchanges
  - `doom_bot/wiki/search.py` - rest search variants + action siteinfo
  - `doom_bot/wiki/admin.py` - block-with-retry pattern
  - `doom_bot/wiki/models.py` - `SearchResult`, `PageSummary`, `SiteInfo`, `PageThumbnail`
  - `doom_bot/ingestor/pipelines/wiki.py` - section split, embedding, recent-changes loop
  - `doom_bot/commands/wiki.py` - `/wiki random|lookup|block`, `WikiLinkView`, `WikiLookupView`

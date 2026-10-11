"""Detecting that a fetch was refused rather than served.

A scraper that only looks at status codes misses most blocking. Anti-bot
services overwhelmingly answer **200** with a challenge page, so the request
looks fine and the extracted content is empty or is boilerplate about enabling
JavaScript. Firecrawl's scrapeURL loop makes the same call: it treats a 2xx with
no extractable content as a failure, and treats 401/403/429 as evidence that the
current identity is inadequate rather than as a final answer.

The distinction that matters here is not "did it fail" but "would trying again
differently help":

* ``HARD_BLOCK``  - refused for who we appear to be. Escalate: new identity,
  stealth, or another engine.
* ``SOFT_BLOCK``  - 200 with a challenge or no content. Same treatment; these
  are the ones a status-code check silently accepts.
* ``NOT_FOUND``   - 404/410. A property of the URL. Escalating wastes time.
* ``OK``          - content was served.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class BlockVerdict(str, Enum):
    OK = "ok"
    SOFT_BLOCK = "soft_block"
    HARD_BLOCK = "hard_block"
    NOT_FOUND = "not_found"

    @property
    def should_escalate(self) -> bool:
        return self in {BlockVerdict.SOFT_BLOCK, BlockVerdict.HARD_BLOCK}


@dataclass(frozen=True)
class BlockAssessment:
    verdict: BlockVerdict
    reason: str = ""
    vendor: str | None = None
    retry_after: int | None = None

    @property
    def blocked(self) -> bool:
        return self.verdict.should_escalate

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "vendor": self.vendor,
            "retry_after": self.retry_after,
        }


OK = BlockAssessment(BlockVerdict.OK)

#: Status codes that mean "not for you, as you are". Firecrawl escalates to a
#: stealth proxy on exactly 401/403/429; 503 is added because that is what most
#: challenge walls return when they refuse outright.
_IDENTITY_REFUSED = {401, 402, 403, 429, 503}
_NOT_FOUND = {404, 410}

# Markers split by how much they prove on their own.
#
# STRONG markers are challenge infrastructure: a page only contains them because
# an interstitial is being served. They stand alone.
#
# WEAK markers appear on ordinary pages too. A contact form legitimately loads
# reCAPTCHA, and a site that sells anti-bot services legitimately discusses "bot
# detection" - spider.cloud tripped exactly that and was flagged while serving
# 13k of content. So a weak marker only counts when the page also failed to yield
# meaningful text, which is what a real wall looks like.
_STRONG_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cloudflare",
        (
            "/cdn-cgi/challenge-platform/",
            "cf-browser-verification",
            "cf_chl_opt",
            "__cf_chl_tk",
            "attention required! | cloudflare",
            "checking your browser before accessing",
        ),
    ),
    ("datadome", ("geo.captcha-delivery.com", "datadome.co/captcha", "dd_cookie_test")),
    ("perimeterx", ("px-captcha", "captcha.px-cloud.net")),
    ("imperva", ("_incapsula_resource", "incapsula incident id")),
    ("aws-waf", ("aws-waf-token", "awswaf/captcha")),
)

_WEAK_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Turnstile sits with reCAPTCHA rather than with the interstitial loaders: a
    # site can embed the widget on a real page (a login or signup form) without
    # anyone being blocked. nowsecure.nl is the pure case - its whole content is
    # the widget - and treating the embed as proof of a block flagged every
    # response there, including the ones that had cleared successfully.
    ("cloudflare-turnstile", ("challenges.cloudflare.com/turnstile", "cf-turnstile-response")),
    ("recaptcha", ("g-recaptcha", "recaptcha/api.js", "recaptcha/enterprise.js")),
    ("hcaptcha", ("hcaptcha.com/1/api.js", "h-captcha-response")),
    ("akamai", ("akamai bot manager", "_abck", "reference&#32;#")),
    ("perimeterx", ("perimeterx.net", "_pxhd")),
    ("imperva", ("visid_incap_",)),
    ("cloudflare", ("cloudflare ray id",)),
    (
        "generic",
        (
            "enable javascript and cookies to continue",
            "verify you are a human",
            "verify you are human",
            "access to this page has been denied",
            "unusual traffic from your computer",
            "our systems have detected unusual traffic",
            "are you a robot",
            "bot detection",
        ),
    ),
)

#: A weak marker only counts if the page yielded less than this much text.
#: Challenge walls are content-free; real pages are not.
_WEAK_MARKER_MAX_EXTRACTED = 500

#: A challenge page is small. Requiring the page to be short as well as matching
#: a marker avoids flagging a real article that merely mentions a captcha.
_MAX_CHALLENGE_HTML = 120_000

_RETRY_AFTER_RE = re.compile(r"^\s*(\d+)\s*$")


def parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    m = _RETRY_AFTER_RE.match(value)
    if m:
        return min(int(m.group(1)), 3600)
    return None


def _find(haystack: str, table) -> tuple[str, str] | None:
    for vendor, markers in table:
        for marker in markers:
            if marker in haystack:
                return vendor, marker
    return None


def assess(
    *,
    status_code: int | None,
    html: str | None = None,
    extracted_length: int = 0,
    retry_after: str | None = None,
    title: str | None = None,
) -> BlockAssessment:
    """Classify one fetched page.

    ``extracted_length`` is the length of whatever text the caller intends to
    return (markdown, or text). It is the signal that catches soft blocks: a
    challenge page yields a 200 and almost nothing extractable.
    """
    after = parse_retry_after(retry_after)

    if status_code in _NOT_FOUND:
        return BlockAssessment(BlockVerdict.NOT_FOUND, f"status {status_code}")

    if status_code in _IDENTITY_REFUSED:
        low = (html or "").lower()[:_MAX_CHALLENGE_HTML]
        hit = _find(low, _STRONG_MARKERS) or _find(low, _WEAK_MARKERS)
        return BlockAssessment(
            BlockVerdict.HARD_BLOCK,
            f"status {status_code}" + (f" ({hit[1]})" if hit else ""),
            vendor=hit[0] if hit else None,
            retry_after=after,
        )

    body = html or ""
    haystack = body.lower()[:_MAX_CHALLENGE_HTML] + " " + (title or "").lower()

    if hit := _find(haystack, _STRONG_MARKERS):
        return BlockAssessment(
            BlockVerdict.SOFT_BLOCK,
            f"challenge infrastructure '{hit[1]}'",
            vendor=hit[0],
            retry_after=after,
        )

    if extracted_length < _WEAK_MARKER_MAX_EXTRACTED:
        if hit := _find(haystack, _WEAK_MARKERS):
            return BlockAssessment(
                BlockVerdict.SOFT_BLOCK,
                f"marker '{hit[1]}' on a page with {extracted_length} chars of text",
                vendor=hit[0],
                retry_after=after,
            )

    # A 2xx that yielded nothing extractable is the classic silent block.
    if status_code is not None and 200 <= status_code < 300 and extracted_length == 0:
        if not body.strip():
            return BlockAssessment(
                BlockVerdict.SOFT_BLOCK, "empty response body", retry_after=after
            )
        return BlockAssessment(
            BlockVerdict.SOFT_BLOCK,
            f"no extractable content from {len(body)} bytes of html",
            retry_after=after,
        )

    return BlockAssessment(BlockVerdict.OK, retry_after=after)

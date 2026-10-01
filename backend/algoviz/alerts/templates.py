"""
Alert message templates
=======================

User-supplied `message_template`s are rendered with a whitelist, not with
`str.format` on arbitrary input:

- placeholders are exactly `{value}`, `{threshold}`, `{field}`, `{symbol}` —
  no attribute or index access (`{value.__class__}`), no conversions (`!r`),
  no nested fields;
- format specs are a bounded subset of the mini-language — align, sign,
  zero-pad, width ≤ 32, grouping, precision ≤ 12, a numeric or string type
  (`{value:,.2f}`, `{value:+.1%}`, `{field:>12}`) — so a template cannot
  allocate a 50 MB string;
- the rendered message is capped at `MAX_MESSAGE` characters.

`template_error()` validates at create/update time; `render()` never raises,
it falls back to the default message.
"""

from __future__ import annotations

import re
import string
from typing import Any

FIELDS = ("value", "threshold", "field", "symbol")
MAX_MESSAGE = 500

_SPEC = re.compile(
    r"""
    ^[<>^=]?          # align
    [+\- ]?           # sign
    0?                # zero padding
    (?P<width>\d{1,2})?
    [,_]?             # grouping
    (?:\.(?P<precision>\d{1,2}))?
    [bdeEfFgGnosxX%]? # type
    $
    """,
    re.VERBOSE,
)


def template_error(template: str) -> str | None:
    """Why `template` is not allowed, or None if it is."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError as exc:
        return f"invalid template: {exc}"
    for _, name, spec, conversion in parts:
        if name is None:
            continue
        if name not in FIELDS:
            return f"unknown placeholder {{{name}}}; use one of " + ", ".join(
                f"{{{f}}}" for f in FIELDS
            )
        if conversion is not None:
            return f"conversions such as !{conversion} are not supported"
        if spec:
            m = _SPEC.match(spec)
            if m is None or "{" in spec:
                return f"unsupported format spec '{spec}' for {{{name}}}"
            if int(m.group("width") or 0) > 32 or int(m.group("precision") or 0) > 12:
                return f"format spec '{spec}' is too wide (width ≤ 32, precision ≤ 12)"
    return None


def render(template: str | None, default: str, **values: Any) -> str:
    """Render a validated template; anything unexpected yields `default`."""
    if not template or template_error(template) is not None:
        return default
    try:
        return template.format(**{k: values.get(k) for k in FIELDS})[:MAX_MESSAGE]
    except (ValueError, TypeError):  # e.g. a numeric spec applied to a categorical value
        return default

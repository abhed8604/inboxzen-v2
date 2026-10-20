"""
Minimal server-side hygiene for untrusted email HTML before it is stored and
rendered in the reader iframe. The iframe sandbox (no allow-scripts) is the
real execution boundary; this keeps hostile markup out of storage entirely.
"""
from selectolax.lexbor import LexborHTMLParser

_STRIP_TAGS = ("script", "iframe", "object", "embed", "applet", "noscript", "frame", "frameset")

def sanitize_email_html(raw: str) -> str:
    """Strips active content: scripts/frames, meta refresh, javascript: URLs,
    inline event handlers. Images, links and CSS are left intact so mail renders."""
    if not raw or "<" not in raw:
        return raw or ""
    try:
        tree = LexborHTMLParser(raw)
    except Exception:
        return ""

    for selector in _STRIP_TAGS:
        for node in tree.css(selector):
            node.decompose()
    # meta refresh = self-navigating iframes; drop the meta entirely
    for node in tree.css("meta"):
        if str(node.attrs.get("http-equiv", "")).lower() in ("refresh", "location"):
            node.decompose()

    for tag in tree.css("*"):
        attrs = tag.attrs
        for key in list(attrs):
            lowered = key.lower()
            value = attrs.get(key) or ""
            if lowered.startswith("on"):
                del attrs[key]
            elif lowered in ("href", "src", "action", "formaction", "xlink:href") and \
                    str(value).strip().lower().startswith(("javascript:", "vbscript:", "data:text/html")):
                del attrs[key]

    # Sandboxed iframes may still navigate themselves — links must open the browser
    for a in tree.css("a"):
        a.attrs["target"] = "_blank"
        a.attrs["rel"] = "noopener noreferrer"

    try:
        return tree.html or ""
    except Exception:
        return ""

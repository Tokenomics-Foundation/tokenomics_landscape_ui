#!/usr/bin/env python3
"""Tokenomics terminology demo server (host: agent@, port 8788).

Serves the pinned v0.0.3 terminology/kiosk demo with clean-path rewrites:
    /                     -> terminology.html (glossary)
    /terminology          -> terminology.html
    /terminology/<slug>   -> terminology.html (page reads slug from path)
    /kpi                  -> terminology.html (KPI mode)
    /kpi/<slug>           -> terminology.html
    /kiosk                -> kiosk.html
    vendor/ data/ assets/ -> static files
No query strings in links. Standard library only.
"""
import http.server
import re

PORT = 8788
ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
VIEWS = re.compile(r"^/(terminology|kpi)(/[^/?]*)?/?$")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def send_head(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/terminology.html"):
            self.path = "/terminology.html"
        elif path == "/kiosk" or path == "/kiosk.html":
            self.path = "/kiosk.html"
        elif VIEWS.match(path):
            self.path = "/terminology.html"
        return super().send_head()

    def log_message(self, format, *args):  # noqa: A002 - base signature
        pass

if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

#!/usr/bin/env python3
"""Data pinning helper for terminology.html (Definitions WG).

    scripts/pin_data.py v0.0.2

Converts the pinned YAML (data/<version>/tokenomics_mindmap.yaml, taken from
a named tag of the tokenomics_mindmap repo) to compact JSON and rewrites ONLY
three things inside terminology.html:

  1. the contents of <script type="application/json" id="tfg-data">
  2. the JS constant  var DATA_VERSION = "v..."
  3. the version note  tokenomics_mindmap.yaml (v...)  in the header comment

This is a one-off maintenance helper, not a page build: terminology.html
stays the complete, hand-editable artifact (per the TF Mini-Tool Guide there
is no build step and no fork). The visible draft pill reads DATA_VERSION at
runtime, so it follows automatically; the "VERSION:" line in the header
comment is a release note and stays hand-edited.

Idempotent: running it again with the same version reports "identical" and
writes nothing. Refuses the conversion if the data text contains an em dash
(U+2014) or en dash (U+2013): house rules say none ship.

YAML parse: PyYAML when available, otherwise node with the vendored
js-yaml.min.js (verified byte-equivalent on v0.0.2). Python 3 stdlib plus
one of those two.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "terminology.html"
DASHES = ("\u2014", "\u2013")


def parse_yaml(path):
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # PyYAML
        return yaml.safe_load(text)
    except ImportError:
        pass
    js = (
        "const y=require('%s');const fs=require('fs');"
        "process.stdout.write(JSON.stringify(y.load(fs.readFileSync('%s','utf8'))));"
        % (ROOT / "vendor" / "js-yaml.min.js", path)
    )
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("pin_data: no PyYAML and node js-yaml failed: %s" % r.stderr.strip()[:300])
    return json.loads(r.stdout)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    ver = sys.argv[1]
    if not ver.startswith("v"):
        ver = "v" + ver
    ypath = ROOT / "data" / ver / "tokenomics_mindmap.yaml"
    if not ypath.is_file():
        sys.exit("pin_data: no vendored YAML at %s (vendor it first: git -C ../tokenomics_mindmap show %s:tokenomics_mindmap.yaml > %s)" % (ypath, ver, ypath))
    data = parse_yaml(ypath)
    if not isinstance(data, dict) or len(data) != 1:
        sys.exit("pin_data: expected exactly one top-level key in %s, got %s" % (ypath, type(data).__name__))
    blob = json.dumps([data], ensure_ascii=True, separators=(",", ":"))
    # House rules: no em/en dashes ship in tool output (check the decoded text).
    if any(d in json.dumps(data) for d in DASHES) or any(d in str(data) for d in DASHES):
        sys.exit("pin_data: the data contains an em/en dash; house rules forbid it, fix the YAML first.")
    if "</script" in blob.lower():
        sys.exit("pin_data: data contains a script-tag sequence and cannot be inlined safely.")

    html = PAGE.read_text(encoding="utf-8")
    new = html
    new, n1 = re.subn(r'(<script type="application/json" id="tfg-data">).*?(</script>)',
                      lambda m: m.group(1) + blob + m.group(2), new, count=1, flags=re.S)
    new, n2 = re.subn(r'var DATA_VERSION = "[^"]*";', 'var DATA_VERSION = "%s";' % ver, new, count=1)
    new, n3 = re.subn(r'tokenomics_mindmap\.yaml \([^)]*\)', 'tokenomics_mindmap.yaml (%s)' % ver, new, count=1)
    if (n1, n2, n3) != (1, 1, 1):
        sys.exit("pin_data: anchor(s) not found (data block=%d, DATA_VERSION=%d, header note=%d); page drifted from the expected shape, fix by hand." % (n1, n2, n3))

    if new == html:
        print("pin_data: %s already pinned to %s (identical, %d bytes, nothing written)" % (PAGE.name, ver, len(html.encode("utf-8"))))
        return
    PAGE.write_text(new, encoding="utf-8")
    print("pin_data: %s pinned to %s (%d -> %d bytes, JSON payload %d bytes)" % (PAGE.name, ver, len(html.encode("utf-8")), len(new.encode("utf-8")), len(blob.encode("utf-8"))))


if __name__ == "__main__":
    main()

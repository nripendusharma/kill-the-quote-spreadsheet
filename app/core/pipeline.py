"""Orchestration + cache. Extraction results are cached to disk so the demo opens instantly;
the 'Re-read' buttons and new uploads always call the model live."""
import json
import time

from . import extract
from .data import ATTACH, DEMO_INBOX, INBOX, STATE

CACHE = STATE / "extractions.json"


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"extractions": {}, "attachments": {}, "meta": {}}


def save_cache(c):
    CACHE.write_text(json.dumps(c, indent=1), encoding="utf-8")


def demo_files(v):
    spec = DEMO_INBOX[v]
    return [(f, (INBOX / f).read_bytes()) for f in spec["files"]], spec["email"], \
           [(f, (ATTACH / f).read_bytes()) for f in spec["attachments"]]


def run_vendor(rfx, v, cache, files=None, email=None, atts=None, label=None):
    """Extract one vendor live and store it in the cache."""
    if files is None:
        files, email, atts = demo_files(v)
    t0 = time.time()
    if atts:
        note = "Attachments received with this reply (the system verifies them separately): " + ", ".join(n for n, _ in atts)
        email = f"{email}\n\n{note}" if email else note
    ex, usage = extract.extract_vendor(rfx, label or rfx["vendors"].get(v, {}).get("name", v), files, email)
    att_out = [extract.extract_attachment(n, d) for n, d in (atts or [])]
    cache["extractions"][v] = ex
    cache["attachments"][v] = att_out
    cache["meta"][v] = dict(files=[n for n, _ in files], attachments=[n for n, _ in (atts or [])],
                            seconds=round(time.time() - t0, 1), **usage)
    save_cache(cache)
    return ex

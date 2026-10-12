"""Runs live extraction for the given vendors (default all) and prints the scorecard. Uses the key in .streamlit/secrets.toml."""
import os, sys, re, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("ANTHROPIC_API_KEY", re.search(r'"(.+)"', (ROOT / ".streamlit/secrets.toml").read_text()).group(1))
from core import pipeline, normalize, scorecard
from core.data import load_rfx, load_last_year, load_answer_key
rfx, ly = load_rfx(), load_last_year()
cache = pipeline.load_cache()
for v in (sys.argv[1:] or list("ABCDE")):
    t = time.time()
    ex = pipeline.run_vendor(rfx, v, cache)
    print(f"{v}: {len(ex['lines'])} lines, {time.time()-t:.0f}s, flags={len(ex['red_flags'])}, unquoted={ex['unquoted_rfx_lines']}", flush=True)
comp = normalize.build(rfx, ly, cache["extractions"], cache["attachments"], rfx["assumptions"], {})
rows = scorecard.score(comp, load_answer_key())
print(json.dumps(scorecard.summary(rows)))
for r in rows:
    if r["outcome"] not in ("correct", "correctly not quoted"):
        print(r)

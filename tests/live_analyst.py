import os, sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("ANTHROPIC_API_KEY", re.search(r'"(.+)"', (ROOT / ".streamlit/secrets.toml").read_text()).group(1))
from core import normalize, pipeline, analyst
from core.data import load_rfx, load_last_year
rfx, ly = load_rfx(), load_last_year(); c = pipeline.load_cache()
a = dict(rfx["assumptions"]); comp = normalize.build(rfx, ly, c["extractions"], c["attachments"], a, {})
an = analyst.Analyst(comp, rfx, ly, dict(assumptions=a, extractions=c["extractions"], attachments=c["attachments"], overrides={}))
for q in sys.argv[1:]:
    print("\n#### Q:", q, flush=True)
    ans, arts = an.ask(q, on_step=lambda s: print("   step:", s, flush=True))
    print(ans); print("artifacts:", [(k, t) for k, t, _ in arts], flush=True)

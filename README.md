# Kill the Quote Spreadsheet

Take-home prototype: an AI co-pilot drafts an RFx, five vendors reply in whatever shape they like
(Excel ignoring the template, letterhead PDF in USD, Word prose, an angled phone photo, a one-line email),
and the system reads every reply into one comparison the buyer can interrogate in plain language,
all the way to a defensible award.

**Design rule:** the model reads and interprets; code does every conversion and sum; a person signs off on anything uncertain.

## Run locally
```
pip install -r requirements.txt
set ANTHROPIC_API_KEY=...        (or .streamlit/secrets.toml)
streamlit run app/app.py
```

## Layout
- `app/core/extract.py` - extraction loop (Claude, structured output, evidence + confidence per number)
- `app/core/normalize.py` - deterministic units / currency / GST / freight / outliers / qualification
- `app/core/optimizer.py` - award scenarios (cheapest per line, constraints, capacity, conditional discounts)
- `app/core/analyst.py` - tool-use loop: SQL over DuckDB, optimiser, charts, award memo
- `app/core/copilot.py` - RFx drafting co-pilot + vendor clarification emails
- `app/core/scorecard.py` - accuracy vs the hand-built answer key
- `data/build_dataset.py` - generates the fabricated dataset (all companies and people fictional)

Plumbing that is stubbed: email sending and receiving. Everything that reads, matches, reasons or answers is a live model call.

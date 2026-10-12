"""The analyst: a tool-use loop over the normalised comparison. The model plans and explains;
SQL, the optimiser and the chart code produce every number."""
import json
import plotly.express as px

from . import llm, normalize, optimizer, store

TOOLS = [
    {"name": "run_sql", "description": "Run a read-only DuckDB SELECT over the comparison tables. Use for any lookup, filter, ranking or aggregate.\n" + store.SCHEMA_DOC,
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["sql", "purpose"],
                      "properties": {"sql": {"type": "string"}, "purpose": {"type": "string", "description": "one line: why you are running this"}}}},
    {"name": "award_scenario", "description": (
        "Compute an award scenario with the deterministic optimiser (cheapest eligible quote per line, optional constraints). "
        "Returns total cost, change vs last year, vendor shares, per-line awards, and warnings (capacity, conditional discounts, untrusted prices). "
        "By default only trusted prices (verified/converted/buyer_confirmed) are eligible. "
        "Use fx_usd_inr / freight_pct overrides for sensitivity questions."),
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["label"],
                      "properties": {
                          "label": {"type": "string", "description": "short name for this scenario, e.g. 'VP split: qualified only'"},
                          "vendors": {"type": "array", "items": {"type": "string"}, "description": "vendor codes A-E to consider; omit for all"},
                          "qualified_only": {"type": "boolean"},
                          "allow_inferred": {"type": "boolean", "description": "allow prices filled from last year"},
                          "allow_review": {"type": "boolean", "description": "allow prices still needing review"},
                          "basis": {"type": "string", "enum": ["landed", "quoted"]},
                          "max_vendor_share_pct": {"type": "number"},
                          "single_vendor": {"type": "string", "description": "award everything to one vendor code"},
                          "exclude_lines": {"type": "array", "items": {"type": "string"}},
                          "fx_usd_inr": {"type": "number"}, "freight_pct": {"type": "number"}}}},
    {"name": "make_chart", "description": "Draw a chart from a SQL result. The chart is shown to the buyer.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["sql", "chart_type", "x", "y", "title"],
                      "properties": {"sql": {"type": "string"}, "chart_type": {"type": "string", "enum": ["bar", "grouped_bar", "stacked_bar", "line", "scatter"]},
                                     "x": {"type": "string"}, "y": {"type": "string"}, "color": {"type": "string"}, "title": {"type": "string"}}}},
    {"name": "export_award_memo", "description": "Save a markdown award recommendation memo for the VP, built from a scenario you already computed. The buyer gets a download button.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["scenario_label", "markdown"],
                      "properties": {"scenario_label": {"type": "string"}, "markdown": {"type": "string"}}}},
]

SYSTEM = """You are a procurement analyst sitting next to a category buyer. The buyer is deciding a corrugated packaging award worth about Rs 4 crore a year, and the VP will challenge the recommendation.

How you work:
- Every number you state must come from a tool result in this conversation. Never do arithmetic in your head; if you need a number, query it or run a scenario.
- Prices carry a status. verified/converted/buyer_confirmed are trusted. inferred = vendor did not restate, filled from last year. review = a human has not yet checked a low-confidence reading. not_quoted = no price. When an answer depends on inferred or review prices, say so plainly and name the lines. Never quietly treat a missing quote as zero or as cheapest.
- Qualification: vendors have pass / fail / unverified from the must-pass questionnaire, cross-checked against attached certificates. "Cleared the questionnaire" means pass.
- Lead with the answer in one or two sentences, then the evidence (a compact table if useful), then caveats. Keep it tight; a busy VP reads this.
- Prefer award_scenario for any "what if we award..." question; use run_sql for lookups. Make a chart when a comparison is easier to see than read.
- If the buyer asks for something the data cannot support (e.g. a price nobody quoted), say what is missing and what would resolve it (often: ask the vendor).
- Amounts: show rupees in lakh or crore (1 crore = 100 lakh = 10,000,000)."""


class Analyst:
    def __init__(self, comp, rfx, last_year, build_args):
        self.rfx, self.ly, self.build_args = rfx, last_year, build_args
        self.set_comp(comp)
        self.messages = []
        self.scenarios = {}

    def set_comp(self, comp):
        self.comp = comp
        self.con = store.connect(store.frames(comp, self.rfx, self.ly))

    def _comp_with(self, fx=None, freight=None):
        if fx is None and freight is None:
            return self.comp
        a = dict(self.build_args["assumptions"])
        if fx is not None:
            a["fx_usd_inr"] = fx
        if freight is not None:
            a["freight_pct_if_extra"] = freight
        return normalize.build(self.rfx, self.ly, self.build_args["extractions"], self.build_args["attachments"], a,
                               self.build_args.get("overrides"))

    def _tool(self, name, inp, artifacts):
        if name == "run_sql":
            df = store.run_sql(self.con, inp["sql"])
            artifacts.append(("table", inp["purpose"], df))
            return df.to_csv(index=False) if len(df) else "(no rows)"
        if name == "award_scenario":
            comp = self._comp_with(inp.get("fx_usd_inr"), inp.get("freight_pct"))
            args = {k: inp[k] for k in ("vendors", "qualified_only", "allow_inferred", "allow_review", "basis",
                                         "max_vendor_share_pct", "single_vendor", "exclude_lines") if k in inp}
            r = optimizer.award(comp, self.rfx, self.ly, **args)
            r["label"] = inp["label"]
            if "fx_usd_inr" in inp or "freight_pct" in inp:
                r["params"]["fx_usd_inr"] = inp.get("fx_usd_inr"); r["params"]["freight_pct"] = inp.get("freight_pct")
            self.scenarios[inp["label"]] = r
            artifacts.append(("scenario", inp["label"], r))
            slim = {k: v for k, v in r.items() if k != "rows"}
            slim["rows"] = [{k: row[k] for k in ("line", "vendor", "price", "annual_value", "status", "change_vs_last_year_pct", "runner_up")} for row in r["rows"]]
            return json.dumps(slim)
        if name == "make_chart":
            df = store.run_sql(self.con, inp["sql"])
            kw = dict(x=inp["x"], y=inp["y"], title=inp["title"])
            if inp.get("color"):
                kw["color"] = inp["color"]
            t = inp["chart_type"]
            if t in ("bar", "grouped_bar", "stacked_bar"):
                fig = px.bar(df, barmode="group" if t == "grouped_bar" else "relative", **kw)
            elif t == "line":
                fig = px.line(df, markers=True, **kw)
            else:
                fig = px.scatter(df, **kw)
            artifacts.append(("chart", inp["title"], fig))
            return f"Chart drawn with {len(df)} rows."
        if name == "export_award_memo":
            artifacts.append(("memo", inp["scenario_label"], inp["markdown"]))
            return "Memo saved; the buyer has a download button."
        raise ValueError(f"unknown tool {name}")

    def ask(self, question, on_step=None):
        """Runs the loop. Returns (final_text, artifacts). on_step(str) gets progress lines for the UI."""
        self.messages.append({"role": "user", "content": question})
        artifacts = []
        for _ in range(12):
            resp = llm.create(self.messages, system=SYSTEM, tools=TOOLS, effort="medium", max_tokens=16000)
            self.messages.append({"role": "assistant", "content": resp.content})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                return llm.text_of(resp), artifacts
            results = []
            for u in uses:
                if on_step:
                    on_step(f"{u.name}: {u.input.get('purpose') or u.input.get('label') or u.input.get('title') or ''}")
                try:
                    out = self._tool(u.name, u.input, artifacts)
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
                except Exception as e:
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": f"Error: {e}", "is_error": True})
            self.messages.append({"role": "user", "content": results})
        return "I stopped after 12 steps without finishing. Try narrowing the question.", artifacts

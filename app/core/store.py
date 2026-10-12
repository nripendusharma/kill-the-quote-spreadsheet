"""Loads the normalised comparison into DuckDB so the analyst can run real SQL over it."""
import duckdb
import pandas as pd


def frames(comp, rfx, last_year, attachments=None):
    lines = pd.DataFrame([dict(line_id=l["id"], description=l["description"], kind=l["kind"], ply=l["ply"], flute=l["flute"],
                               size=l["size"], annual_qty=l["annual_qty"], weight_kg=l["weight_kg"],
                               last_year_price=float(last_year[l["id"]]["price_inr_per_pc_ex_gst"]))
                          for l in rfx["lines"]])
    qty = dict(zip(lines.line_id, lines.annual_qty))
    vinfo = comp["vendors"]
    quotes = pd.DataFrame([dict(vendor=c["vendor"], vendor_name=vinfo[c["vendor"]]["name"], line_id=c["line"], status=c["status"],
                                price_inr_per_pc=None if c["value"] is None else round(c["value"], 3),
                                landed_inr_per_pc=None if c["landed"] is None else round(c["landed"], 3),
                                annual_value_inr=None if c["landed"] is None else round(c["landed"] * qty[c["line"]]),
                                reading_confidence=(c["q"] or {}).get("extraction_confidence"),
                                how_derived="; ".join(c["tags"]), review_reasons="; ".join(c["reasons"]))
                           for c in comp["cells"].values()])
    vendors = pd.DataFrame([dict(vendor=v, name=x["name"], qualification=x["qualification"]["status"],
                                 qualification_issues="; ".join(x["qualification"]["reasons"]),
                                 capacity_t_month=x["capacity_t_month"], freight_extra=x["freight_extra"],
                                 payment_days=x["terms"].get("payment_days"), lead_time_days=x["terms"].get("lead_time_days"),
                                 validity=x["terms"].get("validity"), price_escalation=x["terms"].get("price_escalation"),
                                 discounts="; ".join(f"{d['percent']}% if {d['condition']}" for d in x["terms"].get("discounts", [])),
                                 lines_quoted=x["coverage"], flags=" | ".join(x["flags"]))
                            for v, x in vinfo.items()])
    q = pd.DataFrame([dict(vendor=v, qid=qid, verdict=d["verdict"], note=d["note"])
                      for v, x in vinfo.items() for qid, d in x["qualification"]["detail"].items()])
    alts = pd.DataFrame(comp["alternates"]) if comp["alternates"] else pd.DataFrame(columns=["vendor", "rfx_line_id"])
    att = pd.DataFrame([dict(vendor=v, file=a.get("file"), doc_type=a.get("doc_type"), valid_until=a.get("valid_until"),
                             result=a.get("result"), key_facts=a.get("key_facts"))
                        for v, lst in (attachments or {}).items() for a in lst],
                       columns=["vendor", "file", "doc_type", "valid_until", "result", "key_facts"])
    return dict(lines=lines, quotes=quotes, vendors=vendors, questionnaire=q, alternate_offers=alts, attachments=att)


SCHEMA_DOC = """Tables (DuckDB SQL):
- lines(line_id, description, kind, ply, flute, size, annual_qty, weight_kg, last_year_price)  -- the 30 RFx lines
- quotes(vendor, vendor_name, line_id, status, price_inr_per_pc, landed_inr_per_pc, annual_value_inr, reading_confidence, how_derived, review_reasons)
    status in ('verified','converted','buyer_confirmed','inferred','review','not_quoted'). Prices are INR per piece ex-GST.
    landed = price + assumed freight where the vendor said freight extra. annual_value_inr uses landed price x annual_qty.
- vendors(vendor, name, qualification ['pass','fail','unverified'], qualification_issues, capacity_t_month, freight_extra,
          payment_days, lead_time_days, validity, price_escalation, discounts, lines_quoted, flags)
- questionnaire(vendor, qid, verdict, note)   -- must-pass questions only; Q1/Q2 verdicts are decided from the attachments actually received
- attachments(vendor, file, doc_type, valid_until, result, key_facts)   -- certificates and test reports received, as read by the system
- alternate_offers(vendor, rfx_line_id, price_value, price_unit, currency, deviation, evidence_quote)"""


def connect(fr):
    con = duckdb.connect()
    for name, df in fr.items():
        con.register(name, df)
    return con


def run_sql(con, sql, limit=200):
    s = sql.strip().rstrip(";")
    if not s.lower().startswith(("select", "with")):
        raise ValueError("Only SELECT queries are allowed.")
    df = con.execute(s).fetchdf()
    return df.head(limit)

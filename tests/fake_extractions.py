"""DEV ONLY: builds 'perfect reader' extractions from the answer key so the deterministic layers can be tested
without API calls. Never used by the app."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from core.data import load_rfx, load_answer_key

UNIT = {"per 100 pcs": "per_100", "per pc": "per_piece", "per box": "per_piece", "per kg": "per_kg", "same as last year": "same_as_last_year"}

def fake():
    rfx, key = load_rfx(), load_answer_key()
    out = {}
    for v, info in key["vendors"].items():
        ls = []
        for lid, x in info["lines"].items():
            u = UNIT.get(x["stated_unit"], "same_as_last_year")
            amb = x["stated_unit"].startswith("AMBIGUOUS")
            ls.append(dict(rfx_line_id=lid, vendor_description=lid, match_confidence=0.6 if amb else 0.97,
                           price_value=None if u == "same_as_last_year" else x["stated_price"], price_unit=u, unit_text=x["stated_unit"],
                           currency=x["currency"], gst_inclusive=x["gst_inclusive"], evidence_quote="", evidence_location="",
                           extraction_confidence=0.7 if "handwritten_correction" in x["expected_flags"] else 0.95,
                           uncertainty_reason="ambiguous" if amb else None))
        t = info["terms"]
        disc = [dict(percent=2.5, condition=info["conditional_discount"]["condition"], evidence_quote="")] if v == "B" else []
        qa = {"A": ["yes","yes","yes","yes"], "B": ["yes","yes","yes","yes"], "C": ["no","no","no","no"], "D": ["yes","yes","yes","yes"], "E": ["not_answered"]*4}[v]
        caps = {"A": "300 MT", "B": "900 MT", "C": "35 tonnes", "D": "60 ton/month", "E": ""}
        out[v] = dict(vendor_name=rfx["vendors"][v]["name"], summary="", lines=ls, unquoted_rfx_lines=info.get("missing", []),
                      alternate_offers=[], red_flags=[],
                      terms=dict(delivery=t["delivery"], freight="extra" if v == "E" else "included",
                                 payment_days=t["payment_days"] if isinstance(t["payment_days"], int) else None,
                                 validity=t["validity"], gst_treatment=t["gst"], lead_time_days=None, price_escalation=None,
                                 discounts=disc, evidence=""),
                      questionnaire=[dict(qid=f"Q{i+1}", answer=caps[v] if i == 2 else "x", meets_requirement=a, evidence_quote="") for i, a in enumerate(qa)],
                      stated_total=dict(value=info.get("stated_total_usd"), currency="USD" if v == "B" else None, evidence=None))
    atts = {"A": [dict(doc_type="iso_certificate", valid_until="2027-08-13"), dict(doc_type="test_report")],
            "B": [dict(doc_type="iso_certificate", valid_until="2026-03-31"), dict(doc_type="test_report")],
            "C": [], "D": [dict(doc_type="iso_certificate", valid_until="2029-01-01"), dict(doc_type="test_report")], "E": []}
    return rfx, out, atts

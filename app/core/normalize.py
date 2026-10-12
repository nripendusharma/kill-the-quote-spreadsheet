"""Deterministic layer: units, currency, tax, freight, outliers, qualification.
Every transformation is recorded on the cell so the buyer can see exactly how a number was derived."""
import re
import statistics
from .data import TODAY

TRUST = 0.85          # below this, a human looks
OUTLIER_HI, OUTLIER_LO = 1.5, 0.67

STATUS_ORDER = ["verified", "converted", "buyer_confirmed", "inferred", "review", "not_quoted"]
STATUS_LABEL = {
    "verified": "Verified - read directly, high confidence",
    "converted": "Converted - unit/currency/tax converted by code",
    "buyer_confirmed": "Buyer confirmed or edited",
    "inferred": "Inferred - vendor did not restate; filled from last year",
    "review": "Needs review - low confidence or failed a check",
    "not_quoted": "Not quoted",
}


def _num(text):
    m = re.search(r"(\d[\d,]*\.?\d*)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def build(rfx, last_year, extractions, attachments, assumptions, overrides=None):
    overrides = overrides or {}
    fx, gst, freight = assumptions["fx_usd_inr"], assumptions["gst_pct"] / 100, assumptions["freight_pct_if_extra"] / 100
    lines = {l["id"]: l for l in rfx["lines"]}
    cells, vendors, alternates = {}, {}, []

    for v, ex in extractions.items():
        terms = ex["terms"]
        freight_extra = terms.get("freight") == "extra"
        by_line = {}
        for q in ex["lines"]:
            lid = q["rfx_line_id"]
            if lid not in lines:
                continue
            # keep the higher-confidence entry if the model emitted duplicates
            if lid in by_line and by_line[lid]["extraction_confidence"] >= q["extraction_confidence"]:
                continue
            by_line[lid] = q
        for lid, l in lines.items():
            q = by_line.get(lid)
            key = (v, lid)
            if q is None:
                cells[key] = dict(vendor=v, line=lid, status="not_quoted", value=None, landed=None, tags=[], reasons=[], q=None)
                continue
            tags, reasons = [], []
            val, unit, cur = q["price_value"], q["price_unit"], q["currency"]
            status = "verified"
            guessed = False
            if unit == "other" and q.get("likely_unit") not in (None, "other", "lump_sum"):
                unit, guessed = q["likely_unit"], True
                tags.append(f"Unit not stated by vendor; interpreted as {unit.replace('_', ' ')} - confirm with vendor")
            if unit == "same_as_last_year":
                ly = float(last_year[lid]["price_inr_per_pc_ex_gst"])
                val = ly; status = "inferred"
                tags.append(f"Filled from last year's contract ({last_year[lid]['contract']}): Rs {ly:.2f}")
            elif val is None:
                status = "review"; reasons.append("No price value could be read.")
            else:
                if unit == "per_100":
                    val = val / 100; tags.append("Converted per 100 pcs -> per pc"); status = "converted"
                elif unit == "per_1000":
                    val = val / 1000; tags.append("Converted per 1000 pcs -> per pc"); status = "converted"
                elif unit == "per_kg":
                    rate = val; val = rate * l["weight_kg"]; status = "converted"
                    tags.append(f"Derived: Rs {rate}/kg x {l['weight_kg']} kg board weight (from RFx spec)")
                elif unit in ("lump_sum", "other"):
                    status = "review"; reasons.append(f"Unit '{q['unit_text']}' cannot be converted to per piece automatically.")
                if val is not None and cur == "USD":
                    val = val * fx; tags.append(f"Converted USD -> INR at {fx}"); status = "converted" if status == "verified" else status
                elif cur not in ("INR", "USD"):
                    status = "review"; reasons.append(f"Currency '{cur}' not supported.")
                if val is not None and q["gst_inclusive"] is True:
                    val = val / (1 + gst); tags.append(f"GST {gst*100:.0f}% removed (vendor quoted inclusive)")
                    status = "converted" if status == "verified" else status
            if guessed:
                status = "review"; reasons.append("Unit was not stated by the vendor; value shown uses the most plausible reading.")
            if q["extraction_confidence"] < TRUST:
                status = "review"; reasons.append(f"Reading confidence {q['extraction_confidence']:.2f}")
            if q["match_confidence"] < TRUST:
                status = "review"; reasons.append(f"Line-match confidence {q['match_confidence']:.2f}")
            if q.get("uncertainty_reason") and (q["extraction_confidence"] < 0.95 or q["match_confidence"] < 0.95):
                reasons.append(q["uncertainty_reason"])
            landed = val
            if val is not None and freight_extra:
                landed = val * (1 + freight); tags.append(f"Freight extra: landed cost assumes +{freight*100:.1f}%")
            cells[key] = dict(vendor=v, line=lid, status=status, value=val, landed=landed, tags=tags, reasons=reasons, q=q)
        for a in ex.get("alternate_offers", []):
            alternates.append(dict(vendor=v, **a))

        # ---- vendor-level: totals, qualification
        flags = list(ex.get("red_flags", []))
        st = ex.get("stated_total") or {}
        if st.get("value"):
            pieces = [q for q in by_line.values() if q["price_unit"] == "per_piece" and q["price_value"] is not None]
            if pieces and all((q["currency"] or "") == (st.get("currency") or q["currency"]) for q in pieces):
                calc = sum(q["price_value"] * lines[q["rfx_line_id"]]["annual_qty"] for q in pieces)
                if abs(calc - st["value"]) / max(calc, 1) > 0.002:
                    flags.append(f"Stated total {st['value']:,.0f} does not match the sum of its own lines "
                                 f"({calc:,.0f}); difference {st['value'] - calc:,.0f}. Line prices used, not the total.")
        qual = qualify(rfx, ex, attachments.get(v, []))
        cap = None
        for qa in ex.get("questionnaire", []):
            if qa["qid"] == "Q3":
                cap = _num(qa["answer"])
        vendors[v] = dict(name=ex["vendor_name"], summary=ex["summary"], terms=terms, flags=flags, qualification=qual,
                          capacity_t_month=cap, freight_extra=freight_extra,
                          coverage=sum(1 for lid in lines if cells[(v, lid)]["status"] != "not_quoted"))

    # ---- cross-vendor outlier check (catches unit mix-ups the reader missed)
    for lid in lines:
        vals = [c["value"] for (v, l_), c in cells.items() if l_ == lid and c["value"] is not None]
        if len(vals) >= 3:
            med = statistics.median(vals)
            for (v, l_), c in cells.items():
                if l_ == lid and c["value"] is not None and med > 0:
                    r = c["value"] / med
                    if r > OUTLIER_HI or r < OUTLIER_LO:
                        c["status"] = "review"
                        c["reasons"].append(f"{r:.1f}x the median of other vendors - possible unit or spec mismatch")

    # ---- buyer overrides win, and are logged
    for (v, lid), o in overrides.items():
        c = cells.get((v, lid))
        if not c:
            continue
        if o.get("value") is not None:
            c["value"] = o["value"]
            c["landed"] = o["value"] * (1 + freight) if vendors.get(v, {}).get("freight_extra") else o["value"]
        c["status"] = "buyer_confirmed"
        c["tags"].append(f"Buyer: {o.get('note', 'confirmed')}")
    return dict(cells=cells, vendors=vendors, alternates=alternates)


def qualify(rfx, ex, atts):
    """Must-pass questionnaire rules, cross-checked against attached documents (not just the vendor's say-so)."""
    answers = {q["qid"]: q for q in ex.get("questionnaire", [])}
    iso = [a for a in atts if a.get("doc_type") == "iso_certificate"]
    tests = [a for a in atts if a.get("doc_type") == "test_report"]
    result, reasons = {}, []
    for q in rfx["questionnaire"]:
        if not q["must_pass"]:
            continue
        a = answers.get(q["id"])
        verdict = a["meets_requirement"] if a else "not_answered"
        note = (a["answer"] or "Not answered") if a else "Not answered"
        # Q1/Q2 are decided by what was actually attached, not by the vendor's claim or the reader's guess
        if q["id"] == "Q1":
            if iso:
                valid = [c for c in iso if (c.get("valid_until") or "9999") >= TODAY]
                verdict, note = ("yes", f"Valid certificate attached (until {valid[0].get('valid_until')})") if valid else                                 ("no", f"Attached ISO certificate EXPIRED on {iso[0].get('valid_until')}")
            elif verdict == "yes":
                verdict, note = "unclear", "Claims ISO 9001 but no certificate was attached"
        if q["id"] == "Q2":
            if tests:
                verdict, note = "yes", "Test report attached"
            elif verdict == "yes":
                verdict, note = "unclear", "Says reports are available but none attached"
        result[q["id"]] = dict(verdict=verdict, note=note)
        if verdict != "yes":
            reasons.append(f"{q['id']}: {note}")
    verdicts = [r["verdict"] for r in result.values()]
    status = "fail" if "no" in verdicts else ("unverified" if any(x != "yes" for x in verdicts) else "pass")
    return dict(status=status, detail=result, reasons=reasons)

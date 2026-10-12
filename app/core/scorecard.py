"""Extraction accuracy against the hand-built answer key. Because the dataset was fabricated, ground truth is known:
this measures the reader, and measures whether the review gate catches what the reader gets wrong."""

TOL = 0.01  # 1% on the normalised price


def score(comp, key):
    rows = []
    read = {v for (v, _) in comp["cells"]}
    for v, info in key["vendors"].items():
        if v not in read:
            continue
        truth = info["lines"]
        for lid, t in truth.items():
            c = comp["cells"].get((v, lid))
            if c is None:
                continue
            exp = t["normalised_inr_per_pc_ex_gst"]
            got = c["value"]
            ambiguous = "ambiguous_scope" in t["expected_flags"]
            if ambiguous:
                alt = t.get("alt_if_per_kg")
                correct = got is not None and (abs(got - exp) / exp <= TOL or (alt and abs(got - alt) / alt <= TOL))
            else:
                correct = got is not None and abs(got - exp) / exp <= TOL
            gated = c["status"] in ("review", "inferred")
            rows.append(dict(vendor=v, line=lid, expected=exp, got=None if got is None else round(got, 2), correct=bool(correct),
                             status=c["status"], should_review=ambiguous or "handwritten_correction" in t["expected_flags"],
                             outcome=("correct" if correct and not gated else
                                      "correct, held for review" if correct else
                                      "WRONG but caught by review gate" if gated else "WRONG and trusted")))
        # lines the vendor did not quote: did we invent anything?
        for lid in info.get("missing", []):
            c = comp["cells"].get((v, lid))
            rows.append(dict(vendor=v, line=lid, expected=None, got=None if not c or c["value"] is None else round(c["value"], 2),
                             correct=bool(c and c["status"] == "not_quoted"), status=c["status"] if c else "absent",
                             should_review=False, outcome="correctly not quoted" if c and c["status"] == "not_quoted" else "INVENTED a price"))
    return rows


def summary(rows):
    by = {}
    for r in rows:
        b = by.setdefault(r["vendor"], dict(n=0, correct=0, caught=0, silent_wrong=0))
        b["n"] += 1
        b["correct"] += r["correct"]
        b["caught"] += r["outcome"] == "WRONG but caught by review gate"
        b["silent_wrong"] += r["outcome"] in ("WRONG and trusted", "INVENTED a price")
    return by

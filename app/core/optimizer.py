"""Award scenarios. Pure code: the language model chooses the parameters, never the numbers."""

TRUSTED = ["verified", "converted", "buyer_confirmed"]


def award(comp, rfx, last_year, vendors=None, qualified_only=False, allow_inferred=False, allow_review=False,
          basis="landed", max_vendor_share_pct=None, single_vendor=None, exclude_lines=None):
    lines = {l["id"]: l for l in rfx["lines"] if l["id"] not in (exclude_lines or [])}
    vinfo = comp["vendors"]
    eligible = set(vendors or vinfo.keys())
    if qualified_only:
        eligible = {v for v in eligible if vinfo[v]["qualification"]["status"] == "pass"}
    if single_vendor:
        eligible = {single_vendor}
    statuses = set(TRUSTED) | ({"inferred"} if allow_inferred else set()) | ({"review"} if allow_review else set())
    key = "landed" if basis == "landed" else "value"

    cands = {}
    for lid in lines:
        cs = [c for (v, l_), c in comp["cells"].items()
              if l_ == lid and v in eligible and c[key] is not None and c["status"] in statuses]
        cands[lid] = sorted(cs, key=lambda c: c[key])

    pick = {lid: 0 for lid, cs in cands.items() if cs}
    unawarded = [lid for lid, cs in cands.items() if not cs]

    def value(lid, i):
        return cands[lid][i][key] * lines[lid]["annual_qty"]

    def totals():
        t = {}
        for lid, i in pick.items():
            v = cands[lid][i]["vendor"]
            t[v] = t.get(v, 0) + value(lid, i)
        return t

    moves = []
    if max_vendor_share_pct and not single_vendor:
        cap = max_vendor_share_pct / 100
        for _ in range(200):
            t = totals(); grand = sum(t.values())
            over = [v for v, x in t.items() if x > cap * grand + 1]
            if not over:
                break
            v = max(over, key=lambda x: t[x])
            best = None
            for lid, i in pick.items():
                if cands[lid][i]["vendor"] != v:
                    continue
                for j in range(i + 1, len(cands[lid])):
                    if cands[lid][j]["vendor"] != v:
                        pen = value(lid, j) - value(lid, i)
                        if best is None or pen < best[0]:
                            best = (pen, lid, j)
                        break
            if not best:
                break
            pick[best[1]] = best[2]
            moves.append(f"{best[1]} moved off {vinfo[v]['name']} to respect the {max_vendor_share_pct:.0f}% cap (+Rs {best[0]:,.0f}/yr)")

    rows, warnings = [], []
    used_status = {}
    for lid, i in sorted(pick.items()):
        c = cands[lid][i]; l = lines[lid]
        ly = float(last_year[lid]["price_inr_per_pc_ex_gst"])
        runner = next((x for x in cands[lid] if x["vendor"] != c["vendor"]), None)
        rows.append(dict(line=lid, description=l["description"], qty=l["annual_qty"], vendor=c["vendor"],
                         vendor_name=vinfo[c["vendor"]]["name"], price=round(c[key], 2), annual_value=round(value(lid, i)),
                         status=c["status"], last_year_price=ly,
                         change_vs_last_year_pct=round((c[key] / ly - 1) * 100, 1),
                         runner_up=(f"{runner['vendor']} @ {runner[key]:.2f}" if runner else "none")))
        used_status[c["status"]] = used_status.get(c["status"], 0) + 1
    t = totals(); grand = sum(t.values())
    ly_same = sum(float(last_year[r["line"]]["price_inr_per_pc_ex_gst"]) * r["qty"] for r in rows)
    for v, x in t.items():
        cap_t = vinfo[v].get("capacity_t_month")
        tonnes = sum(lines[r["line"]]["weight_kg"] * r["qty"] for r in rows if r["vendor"] == v) / 1000 / 12
        if cap_t and tonnes > 0.6 * cap_t:
            warnings.append(f"{vinfo[v]['name']} would need ~{tonnes:.0f} t/month against stated capacity {cap_t:.0f} t/month "
                            f"({tonnes / cap_t * 100:.0f}% of capacity).")
        for d in vinfo[v]["terms"].get("discounts", []):
            warnings.append(f"{vinfo[v]['name']} offers {d['percent']}% discount if: {d['condition']}. "
                            f"This scenario awards them Rs {x/1e7:.2f} cr. Check whether the condition is met before counting it.")
    if "inferred" in used_status:
        warnings.append(f"{used_status['inferred']} awarded line(s) use INFERRED prices (vendor did not restate). Confirm before award.")
    if "review" in used_status:
        warnings.append(f"{used_status['review']} awarded line(s) use prices still NEEDING REVIEW.")
    for lid in unawarded:
        warnings.append(f"{lid} could not be awarded: no eligible quote under these filters.")
    excluded_nontrusted = sum(1 for lid in lines for (v, l_), c in comp["cells"].items()
                              if l_ == lid and v in eligible and c["status"] in ("inferred", "review") and c["status"] not in statuses)
    return dict(
        params=dict(vendors=sorted(eligible), qualified_only=qualified_only, allow_inferred=allow_inferred,
                    allow_review=allow_review, basis=basis, max_vendor_share_pct=max_vendor_share_pct, single_vendor=single_vendor),
        total_inr=round(grand), last_year_same_lines_inr=round(ly_same),
        change_vs_last_year_pct=round((grand / ly_same - 1) * 100, 2) if ly_same else None,
        lines_awarded=len(rows), lines_unawarded=unawarded,
        share={vinfo[v]["name"]: dict(value=round(x), pct=round(x / grand * 100, 1)) for v, x in sorted(t.items(), key=lambda z: -z[1])},
        rows=rows, cap_moves=moves, warnings=warnings,
        excluded_untrusted_quotes=excluded_nontrusted,
    )

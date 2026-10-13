"""Negotiation brief: the award engine already knows each vendor's gap to the winning price, so it becomes a target list.
Code sets every target and every ask; the model only writes the message, and the buyer approves it before anything is sent."""
import re
from datetime import date, timedelta

from . import llm
from .optimizer import TRUSTED

MIN_GAP_PCT = 0.5  # gaps smaller than this are not worth a negotiation point


def brief(comp, rfx, last_year, award, basis="landed"):
    """One brief per qualified vendor, against an award scenario (normally the qualified split).
    Savings asks: lines the vendor WINS, priced above the market's lowest trusted quote or last year's price.
    Second-source asks: lines it lost, where matching the winning price makes it a credible backup (no saving)."""
    key = "landed" if basis == "landed" else "value"
    lines = {l["id"]: l for l in rfx["lines"]}
    winner = {r["line"]: r for r in award["rows"]}
    out = {}
    for v, vx in comp["vendors"].items():
        if vx["qualification"]["status"] != "pass":
            continue
        won, savings, second = [], [], []
        for lid, l in lines.items():
            c = comp["cells"].get((v, lid))
            if not c or c[key] is None or c["status"] not in TRUSTED:
                continue
            mine, w = c[key], winner.get(lid)
            if w and w["vendor"] == v:
                won.append(lid)
                market = min((x[key] for (u, l_), x in comp["cells"].items()
                              if l_ == lid and u != v and x[key] is not None and x["status"] in TRUSTED), default=None)
                lyp = float(last_year[lid]["price_inr_per_pc_ex_gst"])
                cands = [(market, "A lower trusted quote exists in this event (that vendor is not qualified)"),
                         (lyp, "Last year's contract price was lower")]
                cands = [(p, why) for p, why in cands if p is not None and p < mine * (1 - MIN_GAP_PCT / 100)]
                if cands:
                    target, why = max(cands, key=lambda z: z[0])  # the nearer, more defensible target
                    savings.append(_ask(lid, l, mine, target, why))
            elif w and w["price"] < mine * (1 - MIN_GAP_PCT / 100):
                second.append(_ask(lid, l, mine, w["price"], "Matching the winning price makes you the second source"))
        savings.sort(key=lambda a: -a["annual_gap"])
        second.sort(key=lambda a: -a["annual_gap"])
        out[v] = dict(vendor=v, name=vx["name"], lines_won=won, savings_asks=savings, second_source_asks=second,
                      term_asks=term_asks(vx), capacity_note=_capacity(vx, lines, won, second),
                      value_won=round(sum(r["annual_value"] for r in award["rows"] if r["vendor"] == v)),
                      saving_if_met=round(sum(a["annual_gap"] for a in savings)))
    return out


def _ask(lid, l, mine, target, why):
    gap = mine - target
    return dict(line=lid, description=l["description"], qty=l["annual_qty"], price=round(mine, 2), target=round(target, 2),
                gap=round(gap, 2), gap_pct=round(gap / mine * 100, 1), annual_gap=round(gap * l["annual_qty"]), why=why)


def _capacity(vx, lines, won, second):
    cap = vx.get("capacity_t_month")
    if not cap:
        return None
    t_won = sum(lines[x]["weight_kg"] * lines[x]["annual_qty"] for x in won) / 1000 / 12
    t_all = t_won + sum(lines[a["line"]]["weight_kg"] * a["qty"] for a in second) / 1000 / 12
    note = f"Current award needs ~{t_won:.0f} t/month of a stated {cap:.0f} t/month."
    if second and t_all > 0.6 * cap:
        note += f" Winning every second-source line too would need ~{t_all:.0f} t/month ({t_all / cap * 100:.0f}%), so confirm capacity first."
    return note


def term_asks(vx):
    """Non-price asks, read from the vendor's own terms. Rules, not model judgment."""
    t, asks = vx["terms"], []
    days = _days(t.get("validity") or "")
    if days is not None and days < 90:
        asks.append(f"Hold prices for the full contract period, or at least 90 days (quoted validity: {t['validity']}).")
    esc = t.get("price_escalation") or ""
    if esc and esc.lower() not in ("none", "no", "fixed", "n/a"):
        asks.append(f"Replace open-ended revision (\"{esc}\") with a quarterly index-linked review that triggers only on a "
                    "kraft paper move of more than 5%.")
    if vx.get("freight_extra"):
        asks.append("Quote delivered to the Bidadi plant, freight included, so prices compare like for like.")
    for d in t.get("discounts") or []:
        asks.append(f"Confirm how the {d['percent']}% discount applies ({d['condition']}) and whether it holds on a split award.")
    return asks


def _days(text):
    m = re.search(r"(\d+)\s*(day|days)", text.lower())
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(month|months)", text.lower())
    return int(m.group(1)) * 30 if m else None


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["subject", "body"],
          "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}}


def counter_offer(rfx, b):
    """Draft the message. Every number is handed in; the model may not add, change or compute any."""
    def fmt(asks):
        return "\n".join(f"- Line {a['line']} ({a['description']}, {a['qty']:,} pcs/yr): your price Rs {a['price']:.2f}/pc, "
                         f"target Rs {a['target']:.2f}/pc" for a in asks) or "- none"
    term_lines = "\n".join(f"- {t}" for t in b["term_asks"]) or "- none"
    won = ", ".join(b["lines_won"]) or "none"
    reply_by = (date.today() + timedelta(days=7)).strftime("%d %b %Y")
    prompt = (f"Write a short, firm but courteous negotiation email from {rfx['buyer']['person']} at {rfx['buyer']['company']} "
              f"to {b['name']} about {rfx['id']}.\n"
              f"Context: they are currently placed to win lines {won}. We want better prices on some of those lines, "
              f"improved terms, and (separately) we would consider them as second source on other lines if they match a target.\n\n"
              f"Price asks on lines they are placed to win:\n{fmt(b['savings_asks'][:8])}\n\n"
              f"Second-source lines (match the target to be considered):\n{fmt(b['second_source_asks'][:5])}\n\n"
              f"Term asks:\n{term_lines}\n\n"
              "Rules: use ONLY the numbers given, never compute or invent any; do not name other vendors or reveal their prices "
              f"beyond the target; do not threaten; ask for a revised quote by {reply_by} (use exactly this date); "
              "list each price ask as its own short line; "
              "plain text, numbered points, no em-dashes, under 230 words.")
    out, _ = llm.structured([{"role": "user", "content": prompt}], SCHEMA, effort="low", max_tokens=4000)
    return out

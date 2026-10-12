"""Kill the Quote Spreadsheet - RFx to defensible award, with the AI loops real and the uncertainty visible."""
import io
import json
import shutil

import pandas as pd
import streamlit as st

from core import analyst as analyst_mod
from core import copilot, normalize, pipeline, scorecard
from core.data import ATTACH, DEMO_INBOX, INBOX, STATE, load_answer_key, load_last_year, load_rfx
from core.ingest import docx_to_text, xlsx_to_text
from core.llm import LLMError

st.set_page_config(page_title="Kill the Quote Spreadsheet", page_icon="📦", layout="wide")

STATUS_COLOR = {"verified": "#d6f0df", "converted": "#dce8fb", "buyer_confirmed": "#e9ddfa",
                "inferred": "#fff0c2", "review": "#f9d3cc", "not_quoted": "#ececec"}
STATUS_SHORT = {"verified": "Verified", "converted": "Converted", "buyer_confirmed": "Buyer-confirmed",
                "inferred": "Inferred", "review": "Needs review", "not_quoted": "Not quoted"}
SEED = STATE / "extractions_seed.json"

# ------------------------------------------------------------------ access + state
try:
    code = st.secrets.get("APP_PASSCODE")
except Exception:
    code = None
if code and not st.session_state.get("authed"):
    st.title("Kill the Quote Spreadsheet")
    if st.text_input("Passcode", type="password") == code:
        st.session_state.authed = True
        st.rerun()
    st.stop()

ss = st.session_state
if "cache" not in ss:
    ss.cache = pipeline.load_cache()
    ss.overrides = {}
    ss.log = []
    ss.chat = []
    ss.copilot = dict(history=[], draft=None, open=[])
    ss.assumptions = None
rfx = load_rfx()
ly = load_last_year()
if ss.assumptions is None:
    ss.assumptions = dict(rfx["assumptions"])


def overrides_tuple():
    return {tuple(k.split("|")): v for k, v in ss.overrides.items()}


def build_comp():
    ex = ss.cache["extractions"]
    if not ex:
        return None
    return normalize.build(rfx, ly, ex, ss.cache["attachments"], ss.assumptions, overrides_tuple())


def log(msg):
    ss.log.append(msg)


def inr(x):
    if x is None:
        return "-"
    return f"Rs {x/1e7:.2f} cr" if abs(x) >= 1e7 else f"Rs {x/1e5:.1f} L"


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 📦 Kill the Quote Spreadsheet")
    st.caption(f"{rfx['id']} · {rfx['title']}")
    page = st.radio("Flow", ["Start here", "1 · Draft the RFx", "2 · Vendor inbox", "3 · Comparison", "4 · Review queue",
                             "5 · Ask the data", "6 · Accuracy scorecard", "Decision log"], label_visibility="collapsed")
    st.divider()
    st.markdown("**Assumptions** (edit and everything recomputes)")
    a = ss.assumptions
    a["fx_usd_inr"] = st.number_input("USD → INR", value=float(a["fx_usd_inr"]), step=0.5)
    a["freight_pct_if_extra"] = st.number_input("Freight % where vendor says 'extra'", value=float(a["freight_pct_if_extra"]), step=0.5)
    a["gst_pct"] = st.number_input("GST % (to strip inclusive quotes)", value=float(a["gst_pct"]), step=1.0)
    st.divider()
    if st.button("↺ Reset demo", help="Restore the seeded extractions and clear buyer edits and chat"):
        if SEED.exists():
            shutil.copy(SEED, pipeline.CACHE)
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()

comp = build_comp()

# ------------------------------------------------------------------ pages
if page == "Start here":
    st.title("Kill the Quote Spreadsheet")
    st.markdown(
        "A buyer drafts an RFx with an AI co-pilot, five vendors reply however they like, and the system reads every reply "
        "into one comparison: **same lines, same units, same currency**. Then the buyer asks questions in plain language, "
        "all the way to an award they can defend.")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**The rule I built around**\n\nThe model *reads and interprets*. Code does *every* conversion and every sum. "
                "A person signs off on anything the model is unsure of.")
    c2.markdown("**What the buyer always sees**\n\nEvery number has a status and a source. Click any cell to see the exact "
                "sentence, cell or photo it came from, and how it was converted.")
    c3.markdown("**What earns trust at Rs 4 crore**\n\nUncertain prices are held out of the award by default. The scorecard "
                "measures the reader against a hand-built answer key.")
    st.markdown("#### Cell status legend")
    cols = st.columns(len(STATUS_COLOR))
    for col, (s_, colr) in zip(cols, STATUS_COLOR.items()):
        col.markdown(f"<div style='background:{colr};padding:8px;border-radius:6px;font-size:13px'><b>{STATUS_SHORT[s_]}</b><br>"
                     f"{normalize.STATUS_LABEL[s_].split(' - ')[-1]}</div>", unsafe_allow_html=True)
    st.markdown("#### The five replies in the inbox")
    st.markdown(
        "- **A · Hosur Corrutech**: Excel that ignores the template, priced *per 100 pieces*, own line order and wording\n"
        "- **B · Pacific Fibre**: letterhead PDF *in USD*, a conditional discount in the footnote, a total that doesn't add up, an expired ISO certificate\n"
        "- **C · Kaveri Kraft**: Word letter with prices in sentences, *27 of 30 lines*, one lower-spec alternate\n"
        "- **D · Sri Lakshmi**: *phone photo of a printed rate card*, at an angle, GST-inclusive, one price corrected by hand\n"
        "- **E · Deccan Corrugators** (incumbent): *“₹42/kg for the 5-ply, 38 for the 3-ply, rest same as last year, freight extra.”*")
    st.info("All companies, people and prices are fabricated. Email sending is stubbed; reading, matching, reasoning and analysis are live model calls.")

elif page == "1 · Draft the RFx":
    st.title("Draft the RFx with the co-pilot")
    cp = ss.copilot
    left, right = st.columns([1, 1.2])
    with left:
        if not cp["history"]:
            st.caption("Try: *We need an annual rate contract for corrugated boxes for the Bidadi plant, about 30 sizes, 3, 5 and 7 ply. "
                       "Last year's supplier was Deccan Corrugators.*")
        for role, text in cp["history"]:
            st.chat_message(role).write(text)
        msg = st.chat_input("Describe what you need to buy")
        if msg:
            with st.spinner("Drafting..."):
                try:
                    draft_json = json.dumps(cp["draft"]) if cp["draft"] else None
                    out = copilot.turn(cp["history"], draft_json, msg)
                    cp["history"] += [("user", msg), ("assistant", out["reply"])]
                    cp["draft"], cp["open"] = out["draft"], out["open_questions"]
                except LLMError as e:
                    st.error(str(e))
            st.rerun()
    with right:
        d = cp["draft"]
        if d:
            st.subheader(d["title"])
            st.write(d["scope"])
            if cp["open"]:
                st.warning("Still open:\n" + "\n".join(f"- {q}" for q in cp["open"]))
            st.dataframe(pd.DataFrame(d["lines"]), hide_index=True, width="stretch")
            st.markdown("**Questionnaire**")
            st.dataframe(pd.DataFrame(d["questionnaire"]), hide_index=True, width="stretch")
            st.markdown("**Terms**"); st.json(d["terms"], expanded=False)
            if st.button("Send to vendors (stubbed email)"):
                log(f"RFx '{d['title']}' sent to {len(d['vendors_to_invite']) or 5} vendors (stubbed outbox).")
                st.success("Queued in the outbox. In this demo, sending is stubbed: the five replies for the issued RFx "
                           f"{rfx['id']} are already in the inbox.")
        else:
            st.info("The live draft appears here as you talk.")
        with st.expander(f"The RFx that was actually issued: {rfx['id']}"):
            st.dataframe(pd.DataFrame(rfx["lines"])[["id", "description", "kind", "ply", "flute", "size", "annual_qty", "grade", "weight_kg"]],
                         hide_index=True, width="stretch")
            st.dataframe(pd.DataFrame(rfx["questionnaire"]), hide_index=True, width="stretch")
            st.json(rfx["terms"])

elif page == "2 · Vendor inbox":
    st.title("Vendor inbox")
    st.caption("Each reply as it arrived. 'Read with AI' sends the raw files to the model live; results are cached so the demo opens fast.")
    vendors = sorted(set(DEMO_INBOX) | set(ss.cache["extractions"]))
    if st.button("Read ALL replies with AI (live, ~2-3 min)"):
        prog = st.progress(0.0)
        for i, v in enumerate(DEMO_INBOX):
            try:
                pipeline.run_vendor(rfx, v, ss.cache)
                log(f"Re-read vendor {v} live.")
            except LLMError as e:
                st.error(f"{v}: {e}")
            prog.progress((i + 1) / len(DEMO_INBOX))
        st.rerun()
    for v in vendors:
        ex = ss.cache["extractions"].get(v)
        meta = ss.cache["meta"].get(v, {})
        name = (ex or {}).get("vendor_name") or rfx["vendors"].get(v, {}).get("name", v)
        with st.expander(f"**{v} · {name}**" + (f" · read {len(ex['lines'])} priced lines" if ex else " · not read yet"), expanded=False):
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown("**What arrived**")
                files = meta.get("files") or DEMO_INBOX.get(v, {}).get("files", [])
                for f in files:
                    p = INBOX / f
                    if not p.exists():
                        st.write(f"• {f} (uploaded)"); continue
                    st.write(f"• {f}")
                    if p.suffix.lower() in (".jpg", ".png"):
                        st.image(str(p), width=360)
                    elif p.suffix == ".txt":
                        st.code(p.read_text(encoding="utf-8"), language=None)
                    elif p.suffix == ".docx":
                        st.text(docx_to_text(p.read_bytes())[:1500] + " ...")
                    elif p.suffix == ".xlsx":
                        st.text(xlsx_to_text(p.read_bytes())[:1500] + " ...")
                    st.download_button("Download original", p.read_bytes(), file_name=f, key=f"dl{v}{f}")
                for f in meta.get("attachments") or DEMO_INBOX.get(v, {}).get("attachments", []):
                    st.write(f"📎 {f}")
            with c2:
                if v in DEMO_INBOX and st.button("Read with AI (live)", key=f"run{v}"):
                    with st.spinner("Reading..."):
                        try:
                            pipeline.run_vendor(rfx, v, ss.cache); log(f"Re-read vendor {v} live.")
                        except LLMError as e:
                            st.error(str(e))
                    st.rerun()
                if ex:
                    st.markdown(f"**Model's read:** {ex['summary']}")
                    if meta:
                        st.caption(f"{meta.get('seconds','?')} s · {meta.get('input_tokens','?')} in / {meta.get('output_tokens','?')} out tokens")
                    if ex["red_flags"]:
                        st.warning("\n".join(f"- {f}" for f in ex["red_flags"]))
                    if ex["unquoted_rfx_lines"]:
                        st.write("Not quoted:", ", ".join(ex["unquoted_rfx_lines"]))
                    st.json(ex["terms"], expanded=False)
                    for a_ in ss.cache["attachments"].get(v, []):
                        st.write(f"📎 {a_['file']}: {a_['doc_type']}, valid until {a_.get('valid_until') or 'n/a'}")
    st.divider()
    st.subheader("Upload a new reply")
    st.caption("Bring your own ugly quote. Any of PDF, Excel, Word, photo, or pasted email text.")
    with st.form("upload"):
        target = st.text_input("Vendor code (A-E to replace a reply, or a new letter like F)", value="F").strip().upper()[:2]
        vname = st.text_input("Vendor name", value="New vendor")
        ups = st.file_uploader("Quote files", accept_multiple_files=True)
        atts = st.file_uploader("Certificates / test reports (optional)", accept_multiple_files=True)
        body = st.text_area("Email body (optional)")
        go = st.form_submit_button("Read with AI")
    if go and (ups or body):
        files = [(u.name, u.getvalue()) for u in (ups or [])]
        if body and not files:
            files = [("email.txt", body.encode())]; body = None
        with st.spinner("Reading..."):
            try:
                pipeline.run_vendor(rfx, target, ss.cache, files=files, email=body,
                                    atts=[(u.name, u.getvalue()) for u in (atts or [])], label=vname)
                ss.cache["meta"][target]["files"] = [n for n, _ in files]
                log(f"New reply read for vendor {target} ({vname}).")
                st.success("Read. See Comparison.")
            except LLMError as e:
                st.error(str(e))

elif comp is None:
    st.warning("No replies have been read yet. Go to Vendor inbox and click 'Read ALL replies with AI'.")

elif page == "3 · Comparison":
    st.title("Side-by-side comparison")
    vinfo = comp["vendors"]
    vcodes = sorted(vinfo)
    basis = st.radio("Price basis", ["Landed (incl. assumed freight)", "Quoted"], horizontal=True)
    key = "landed" if basis.startswith("Landed") else "value"
    trusted_only = st.toggle("Highlight cheapest using trusted prices only", value=True)
    rows, styles = [], []
    for l in rfx["lines"]:
        r = {"Line": l["id"], "Item": l["description"], "Spec": f"{l['ply']}P {l['flute']} · {l['size'].split(' (')[0]}",
             "Qty/yr": f"{l['annual_qty']:,}", "Last yr": f"{float(ly[l['id']]['price_inr_per_pc_ex_gst']):.2f}"}
        srow = {}
        ok = [comp["cells"][(v, l["id"])] for v in vcodes if comp["cells"][(v, l["id"])][key] is not None and
              (not trusted_only or comp["cells"][(v, l["id"])]["status"] in ("verified", "converted", "buyer_confirmed"))]
        best = min((c[key] for c in ok), default=None)
        for v in vcodes:
            c = comp["cells"][(v, l["id"])]
            r[v] = "-" if c[key] is None else f"{c[key]:.2f}"
            srow[v] = f"background-color:{STATUS_COLOR[c['status']]}" + (";font-weight:700;border:2px solid #1a7f37" if best is not None and c[key] == best else "")
        rows.append(r); styles.append(srow)
    df = pd.DataFrame(rows)
    sty = pd.DataFrame("", index=df.index, columns=df.columns)
    for i, srow in enumerate(styles):
        for v, s_ in srow.items():
            sty.loc[i, v] = s_
    st.caption("Rs per piece, ex-GST. Colour = status (legend on Start here). **Bold green border** = cheapest per line. "
               "Pick a cell below to see exactly where its number came from.")
    st.dataframe(df.style.apply(lambda _: sty, axis=None), hide_index=True, width="stretch", height=1090)

    st.subheader("Vendors")
    vt = []
    for v in vcodes:
        x = vinfo[v]
        tot = sum((comp["cells"][(v, l['id'])][key] or 0) * l["annual_qty"] for l in rfx["lines"])
        vt.append({"Vendor": f"{v} · {x['name']}", "Lines quoted": f"{x['coverage']}/30", "Qualification": x["qualification"]["status"].upper(),
                   "Why": "; ".join(x["qualification"]["reasons"]) or "all must-pass met",
                   "Capacity t/mo": x["capacity_t_month"], "Payment days": x["terms"].get("payment_days"),
                   "Freight": x["terms"].get("freight"), "Value of quoted lines": inr(tot),
                   "Needs review": sum(1 for (vv, _), c in comp["cells"].items() if vv == v and c["status"] in ("review", "inferred"))})
    st.dataframe(pd.DataFrame(vt), hide_index=True, width="stretch")
    for v in vcodes:
        for f in vinfo[v]["flags"]:
            st.warning(f"**{v}**: {f}")
    if comp["alternates"]:
        st.subheader("Alternate offers (not like-for-like, kept out of the comparison)")
        st.dataframe(pd.DataFrame(comp["alternates"]), hide_index=True, width="stretch")

    st.subheader("Cell inspector")
    c1, c2 = st.columns(2)
    iv = c1.selectbox("Vendor", vcodes, format_func=lambda v: f"{v} · {vinfo[v]['name']}")
    il = c2.selectbox("Line", [l["id"] for l in rfx["lines"]],
                      format_func=lambda i: f"{i} · {next(l['description'] for l in rfx['lines'] if l['id'] == i)}")
    c = comp["cells"][(iv, il)]
    st.markdown(f"<div style='background:{STATUS_COLOR[c['status']]};padding:10px;border-radius:6px'>"
                f"<b>{STATUS_SHORT[c['status']]}</b> · quoted Rs {c['value'] if c['value'] is None else round(c['value'],2)} · "
                f"landed Rs {c['landed'] if c['landed'] is None else round(c['landed'],2)} per pc</div>", unsafe_allow_html=True)
    q = c["q"]
    if q:
        st.markdown(f"**Vendor wrote:** “{q['evidence_quote']}”  \n**Where:** {q['evidence_location']}  \n"
                    f"**Read as:** {q['price_value']} {q['currency']} {q['price_unit']} ({q['unit_text']}), GST inclusive: {q['gst_inclusive']}  \n"
                    f"**Confidence:** reading {q['extraction_confidence']:.2f} · line match {q['match_confidence']:.2f}")
        for t in c["tags"]:
            st.write("→", t)
        for r_ in c["reasons"]:
            st.write("⚠", r_)
        src = [f for f in (ss.cache["meta"].get(iv, {}).get("files") or DEMO_INBOX.get(iv, {}).get("files", [])) if f.lower().endswith((".jpg", ".png"))]
        if src and (INBOX / src[0]).exists():
            st.image(str(INBOX / src[0]), caption="Source photo", width=520)
    else:
        st.write("No price from this vendor for this line.")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="comparison", index=False)
        pd.DataFrame(vt).to_excel(w, sheet_name="vendors", index=False)
        pd.DataFrame([dict(vendor=v_, line=l_, status=c_["status"], price=c_["value"], landed=c_["landed"],
                           how="; ".join(c_["tags"]), review="; ".join(c_["reasons"])) for (v_, l_), c_ in comp["cells"].items()]
                     ).to_excel(w, sheet_name="audit_trail", index=False)
    st.download_button("⬇ Export comparison + audit trail (Excel)", buf.getvalue(), file_name=f"{rfx['id']}_comparison.xlsx")

elif page == "4 · Review queue":
    st.title("Review queue")
    items = [c for c in comp["cells"].values() if c["status"] in ("review", "inferred")]
    st.caption(f"{len(items)} prices are held out of any award until a person looks. Confirm, correct, or ask the vendor. "
               "Every action is logged.")
    for v in sorted({c["vendor"] for c in items}):
        vi = [c for c in items if c["vendor"] == v]
        st.subheader(f"{v} · {comp['vendors'][v]['name']}  ({len(vi)})")
        for c in vi:
            q = c["q"] or {}
            with st.container(border=True):
                a1, a2 = st.columns([2, 1])
                a1.markdown(f"**{c['line']}** · {STATUS_SHORT[c['status']]} · system value Rs {c['value'] if c['value'] is None else round(c['value'], 2)}  \n"
                            f"Vendor wrote: “{q.get('evidence_quote', '')}” ({q.get('evidence_location', '')})  \n"
                            + "  \n".join(f"⚠ {r_}" for r_ in c["reasons"] + ([t for t in c["tags"] if "last year" in t]) ))
                newv = a2.number_input("Correct value (Rs/pc ex-GST)", value=float(c["value"] or 0.0), key=f"nv{v}{c['line']}", step=0.01)
                b1, b2 = a2.columns(2)
                if b1.button("Confirm", key=f"ok{v}{c['line']}"):
                    ss.overrides[f"{v}|{c['line']}"] = dict(value=newv, note=f"confirmed at Rs {newv:.2f}")
                    log(f"Buyer confirmed {v}/{c['line']} at Rs {newv:.2f} (system had {c['value']}).")
                    st.rerun()
                if b2.button("Ask vendor", key=f"ask{v}{c['line']}"):
                    ss.setdefault("asks", {}).setdefault(v, []).append(
                        f"Line {c['line']}: please confirm your price. We read '{q.get('evidence_quote', '')}'. Issue: {'; '.join(c['reasons']) or 'not restated'}")
                    log(f"Queued clarification for {v}/{c['line']}.")
        issues = ss.get("asks", {}).get(v, []) + [f"Questionnaire {r_}" for r_ in comp["vendors"][v]["qualification"]["reasons"]]
        if comp["vendors"][v]["freight_extra"]:
            issues.append("Freight: how is it charged (per trip, per kg, % of value) to the Bidadi plant?")
        if st.button(f"Draft one clarification email to {v} covering everything open", key=f"mail{v}"):
            with st.spinner("Drafting..."):
                try:
                    m = copilot.clarification_email(rfx, comp["vendors"][v]["name"], issues or ["Please confirm the prices listed in your reply."])
                    ss.setdefault("mails", {})[v] = m
                    log(f"Drafted clarification email to {v} ({len(issues)} questions).")
                except LLMError as e:
                    st.error(str(e))
        if ss.get("mails", {}).get(v):
            m = ss.mails[v]
            st.text_area("Draft (stubbed: not sent)", f"Subject: {m['subject']}\n\n{m['body']}", height=220, key=f"ta{v}")
    st.divider()
    st.subheader("Vendors not yet qualified")
    for v, x in comp["vendors"].items():
        if x["qualification"]["status"] != "pass":
            st.write(f"**{v} · {x['name']}**: {x['qualification']['status'].upper()}. " + "; ".join(x["qualification"]["reasons"]))

elif page == "5 · Ask the data":
    st.title("Ask the data")
    build_args = dict(assumptions=ss.assumptions, extractions=ss.cache["extractions"], attachments=ss.cache["attachments"],
                      overrides=overrides_tuple())
    if "analyst" not in ss:
        ss.analyst = analyst_mod.Analyst(comp, rfx, ly, build_args)
    ss.analyst.build_args = build_args; ss.analyst.set_comp(comp)
    sugg = ["Which vendors quoted all 30 lines, and what is missing from the others?",
            "How confident are we in Sri Lakshmi's prices?",
            "What if we split it, cheapest per line, but only among vendors who cleared the quality questionnaire?",
            "Compare that with giving everything to one vendor. Show a chart.",
            "Cap any single vendor at 60% of spend. What does that cost us?",
            "What happens to the award if the rupee weakens to 92 per dollar?",
            "Write the award recommendation memo for my VP."]
    cols = st.columns(2)
    picked = None
    for i, s_ in enumerate(sugg):
        if cols[i % 2].button(s_, key=f"sg{i}", width="stretch"):
            picked = s_

    def render(arts):
        for kind, title, obj in arts:
            if kind == "table":
                with st.expander(f"SQL · {title}"):
                    st.dataframe(obj, hide_index=True, width="stretch")
            elif kind == "chart":
                st.plotly_chart(obj, width="stretch")
            elif kind == "scenario":
                with st.expander(f"Scenario · {title} · {inr(obj['total_inr'])} ({obj['change_vs_last_year_pct']:+.1f}% vs last year)"):
                    st.write(obj["share"])
                    for w_ in obj["warnings"]:
                        st.warning(w_)
                    st.dataframe(pd.DataFrame(obj["rows"]), hide_index=True, width="stretch")
                    buf = io.BytesIO(); pd.DataFrame(obj["rows"]).to_excel(buf, index=False)
                    st.download_button("⬇ Scenario (Excel)", buf.getvalue(), file_name=f"scenario_{title[:30]}.xlsx", key=f"x{id(obj)}")
            elif kind == "memo":
                st.download_button(f"⬇ Award memo: {title}", obj.encode(), file_name="award_memo.md", key=f"m{id(obj)}")

    for role, text, arts in ss.chat:
        with st.chat_message(role):
            st.markdown(text)
            render(arts)
    q = st.chat_input("Ask anything about the quotes") or picked
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            steps = st.status("Working...", expanded=False)
            try:
                ans, arts = ss.analyst.ask(q, on_step=lambda s_: steps.write(s_))
                steps.update(label="Done", state="complete")
            except LLMError as e:
                ans, arts = f"Error: {e}", []
            st.markdown(ans)
            render(arts)
        ss.chat += [("user", q, []), ("assistant", ans, arts)]
        log(f"Analyst asked: {q}")

elif page == "6 · Accuracy scorecard":
    st.title("Accuracy scorecard")
    st.caption("The dataset is fabricated, so I know the right answer for every cell. This page measures the reader on the CURRENT "
               "extraction, and whether the review gate catches what it gets wrong. Buyer edits are excluded.")
    clean = normalize.build(rfx, ly, ss.cache["extractions"], ss.cache["attachments"], rfx["assumptions"], {})
    rows = scorecard.score(clean, load_answer_key())
    summ = scorecard.summary(rows)
    df = pd.DataFrame([dict(vendor=v, format=load_answer_key()["vendors"][v]["format"], cells=b["n"],
                            correct=f"{b['correct']}/{b['n']} ({b['correct']/b['n']*100:.0f}%)",
                            wrong_but_caught=b["caught"], wrong_and_trusted=b["silent_wrong"]) for v, b in summ.items()])
    tot = sum(b["n"] for b in summ.values()); cor = sum(b["correct"] for b in summ.values())
    silent = sum(b["silent_wrong"] for b in summ.values()); caught = sum(b["caught"] for b in summ.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Cells read correctly", f"{cor}/{tot}", f"{cor/tot*100:.1f}%")
    m2.metric("Errors caught by the review gate", caught)
    m3.metric("Errors that slipped through as trusted", silent, delta_color="inverse")
    st.dataframe(df, hide_index=True, width="stretch")
    bad = [r for r in rows if r["outcome"] not in ("correct", "correctly not quoted")]
    if bad:
        st.subheader("Every cell that was not a clean pass")
        st.dataframe(pd.DataFrame(bad), hide_index=True, width="stretch")

elif page == "Decision log":
    st.title("Decision log")
    st.caption("Everything the buyer did in this session, in order. This is what goes in the award file.")
    for i, m in enumerate(ss.log, 1):
        st.write(f"{i}. {m}")
    if not ss.log:
        st.write("Nothing yet.")
    if ss.overrides:
        st.subheader("Buyer overrides")
        st.json(ss.overrides)

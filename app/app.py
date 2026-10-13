"""Kill the Quote Spreadsheet - RFx to defensible award, with the AI loops real and the uncertainty visible."""
import io
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import streamlit as st

import ui
from core import analyst as analyst_mod
from core import copilot, normalize, optimizer, pipeline, scorecard
from core.data import DEMO_INBOX, INBOX, STATE, load_answer_key, load_last_year, load_rfx
from core.ingest import docx_to_text
from core.llm import LLMError
from ui import STATUS, TRUSTED, esc, inr, md

st.set_page_config(page_title="Quote Desk · RFQ-PKG-2026-014", page_icon=":material/inventory_2:", layout="wide")
ui.inject()

SEED = STATE / "extractions_seed.json"
GRID = {"A": "Hosur", "B": "Pacific", "C": "Kaveri", "D": "Sri Lakshmi", "E": "Deccan"}
SHORT = {"A": "Hosur Corrutech", "B": "Pacific Fibre", "C": "Kaveri Kraft", "D": "Sri Lakshmi", "E": "Deccan Corrugators"}
FORMAT = {"A": "Excel, own layout, per 100 pcs", "B": "PDF in USD", "C": "Word letter", "D": "Phone photo of rate card",
          "E": "Two-line email (incumbent)"}

# ------------------------------------------------------------------ access
try:
    code = st.secrets.get("APP_PASSCODE")
except Exception:
    code = None
if code and not st.session_state.get("authed"):
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.space("large")
        st.image(str(Path(__file__).resolve().parent / "assets" / "logo.svg"), width=190)
        md("<div class='muted' style='margin:6px 0 18px 0'>From RFx to a defensible award. "
           "Sign in to the corrugated packaging sourcing event.</div>")
        with st.form("signin", border=True):
            pw = st.text_input("Passcode", type="password", placeholder="Enter the passcode from the email")
            if st.form_submit_button("Continue", type="primary", width="stretch"):
                if pw == code:
                    st.session_state.authed = True
                    st.rerun()
                st.error("That passcode didn't match.")
    st.stop()

# ------------------------------------------------------------------ state
ss = st.session_state
if "cache" not in ss:
    ss.cache = pipeline.load_cache()
    ss.overrides, ss.log, ss.chat = {}, [], []
    ss.copilot = dict(history=[], draft=None, open=[])
    ss.asks, ss.mails, ss.sent = {}, {}, {}
    ss.assumptions = None
    ss.award_choice = None
    ss.issued_draft = False
rfx = load_rfx()
ly = load_last_year()
if ss.assumptions is None:
    ss.assumptions = dict(rfx["assumptions"])
LINES = {l["id"]: l for l in rfx["lines"]}


def overrides_tuple():
    return {tuple(k.split("|")): v for k, v in ss.overrides.items()}


def build_comp():
    ex = ss.cache["extractions"]
    if not ex:
        return None
    return normalize.build(rfx, ly, ex, ss.cache["attachments"], ss.assumptions, overrides_tuple())


def log(msg, kind="action"):
    ss.log.append(dict(time=datetime.now().strftime("%H:%M"), msg=msg, kind=kind))


@st.cache_data
def pdf_pages(path, limit=2):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    return [doc[i].render(scale=1.6).to_pil() for i in range(min(limit, len(doc)))]


@st.cache_data
def xlsx_frame(path):
    df = pd.read_excel(path, header=None).fillna("")
    df.columns = [chr(65 + i) if i < 26 else str(i) for i in range(len(df.columns))]
    return df.astype(str)


@st.cache_data
def docx_text(path):
    import re
    return re.sub(r"\[para \d+\] ?", "", docx_to_text(Path(path).read_bytes()))


def gname(v):
    return GRID.get(v) or short(v)


def money(x):
    return "–" if x is None else f"₹{x:.2f}"


def short(v):
    if v in SHORT:
        return SHORT[v]
    return (comp["vendors"].get(v, {}).get("name") if comp else None) or rfx["vendors"].get(v, {}).get("name", v)


def open_items(c_):
    return [c for c in c_["cells"].values() if c["status"] in ("review", "inferred")]


def ly_total():
    return sum(float(ly[l]["price_inr_per_pc_ex_gst"]) * LINES[l]["annual_qty"] for l in LINES)


def next_link(page, label):
    st.space("small")
    _, r = st.columns([3, 1])
    r.page_link(page, label=label, icon=":material/arrow_forward:", width="stretch")


comp = build_comp()


def need_data():
    if comp is None:
        st.info("No vendor replies have been read yet. Open **Responses** and read them.")
        st.page_link(P["responses"], label="Go to Responses", icon=":material/inbox:")
        return True
    return False


# ================================================================== pages
def overview():
    n_read = len(ss.cache["extractions"])
    items = open_items(comp) if comp else []
    md(f"<div class='eyebrow'>{rfx['id']} · Closed {datetime.fromisoformat(rfx['due']).strftime('%d %b')} · In evaluation</div>")
    st.title("Corrugated packaging, FY 2026-27", anchor=False)
    md(f"<div class='sub'>Annual rate contract for the Bidadi plant. 30 lines across 3, 5 and 7-ply boxes, partitions and pads. "
       f"Five vendors replied, each in their own format. Last year this basket cost <b>{inr(ly_total())}</b>.</div>")

    best = optimizer.award(comp, rfx, ly, qualified_only=True) if comp else None
    priced = sum(1 for c in comp["cells"].values() if c["status"] != "not_quoted") if comp else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Replies read", f"{n_read} of 5", border=True)
    k2.metric("Prices on one basis", priced, help="Per piece, INR, ex-GST, freight included. Converted by code, not by the model.", border=True)
    k3.metric("Waiting on you", len(items), help="Prices held out of any award until a person looks", border=True)
    if best and best["total_inr"]:
        k4.metric("Best qualified award", inr(best["total_inr"]), f"{best['change_vs_last_year_pct']:+.2f}% vs last year",
                  delta_color="inverse", border=True)
    else:
        k4.metric("Best qualified award", "–", border=True)

    decided = ss.award_choice is not None
    ui.steps([
        ("done", "Draft the RFx", "Issued 1 Oct to 5 vendors"),
        ("done" if n_read >= 5 else "now", "Collect replies", f"{n_read} of 5 read by AI"),
        ("done" if comp else "todo", "Compare", f"{priced} prices normalised"),
        ("done" if comp and not items else ("now" if comp else "todo"), "Resolve", f"{len(items)} need a decision" if items else "Nothing open"),
        ("done" if decided else ("now" if comp and not items else "todo"), "Decide", ss.award_choice or "Pick an award"),
    ])

    if not comp:
        target, t, d = P["responses"], "Read the vendor replies", "The AI reads each reply as it arrived and lines it up with the RFx."
    elif items:
        target, t, d = P["resolve"], f"{len(items)} prices need your decision", (
            "They are excluded from every award until you confirm them or ask the vendor. Most are Deccan's \"rest same as last year\".")
    elif not decided:
        target, t, d = P["decide"], "Ready to decide", "Every price is trusted. Compare award options and record a recommendation."
    else:
        target, t, d = P["audit"], "Recommendation recorded", f"{ss.award_choice}. The audit trail is ready for the award file."
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    with c1:
        md(f"<div class='next'><div class='t'>{esc(t)}</div><div class='d'>{esc(d)}</div></div>")
    if c2.button("Open", type="primary", icon=":material/arrow_forward:", width="stretch", key="next_cta"):
        st.switch_page(target)

    if comp:
        st.subheader("Vendors", anchor=False)
        cols = st.columns(len(comp["vendors"]))
        for col, (v, x) in zip(cols, sorted(comp["vendors"].items())):
            n_open = sum(1 for c in items if c["vendor"] == v)
            with col.container(border=True, height="stretch"):
                md(f"<div class='vcard'><div class='name'>{esc(short(v))}</div>"
                   f"<div class='meta'>{esc(FORMAT.get(v, 'Uploaded reply'))}</div>"
                   f"{ui.qual_tag(x['qualification']['status'])} {ui.tag(str(x['coverage']) + '/30 lines')}"
                   + (f" {ui.pill('review', str(n_open) + ' open')}" if n_open else "") + "</div>")

    st.subheader("How it works", anchor=False)
    md("<div class='how'>"
       "<div class='c'><div class='h'>1. The AI reads anything</div><div class='muted'>Excel, PDF, Word, a phone photo or a two-line email. "
       "It finds each price, matches it to an RFx line and quotes the exact words it saw.</div></div>"
       "<div class='c'><div class='h'>2. Code does the maths</div><div class='muted'>Per-100 to per-piece, USD to INR, GST out, freight in, "
       "₹/kg to ₹/box from board weight. Every conversion is written on the cell.</div></div>"
       "<div class='c'><div class='h'>3. You sign off on doubt</div><div class='muted'>Anything uncertain is held out of the award until "
       "you confirm it or ask the vendor. Every decision lands in the audit trail.</div></div></div>")
    ui.footer()


def draft():
    ui.header("Step 1 · Draft", "Draft the RFx",
              "Describe what you need in plain words. The co-pilot keeps a complete, sendable RFx up to date and asks only what blocks sending.")
    t1, t2 = st.tabs(["New RFx with co-pilot", f"Issued · {rfx['id']}"])
    cp = ss.copilot
    with t1:
        left, right = st.columns([1, 1.25], gap="large")
        with left:
            chat = st.container(height=520, border=True)
            with chat:
                if not cp["history"]:
                    md("<div class='muted'>Start with what you know. For example:</div>")
                    if st.button("We need an annual rate contract for corrugated boxes for the Bidadi plant, about 30 sizes, 3, 5 and 7 ply. "
                                 "Last year's supplier was Deccan Corrugators.", icon=":material/lightbulb:", key="starter"):
                        ss.cp_pending = ("We need an annual rate contract for corrugated boxes for the Bidadi plant, about 30 sizes, "
                                         "3, 5 and 7 ply. Last year's supplier was Deccan Corrugators.")
                        st.rerun()
                for role, text in cp["history"]:
                    st.chat_message(role, avatar=":material/person:" if role == "user" else ":material/auto_awesome:").write(text)
            msg = st.chat_input("Describe what you need to buy", key="cp_in") or ss.pop("cp_pending", None)
            if msg:
                with st.spinner("Updating the draft..."):
                    try:
                        out = copilot.turn(cp["history"], json.dumps(cp["draft"]) if cp["draft"] else None, msg)
                        cp["history"] += [("user", msg), ("assistant", out["reply"])]
                        cp["draft"], cp["open"] = out["draft"], out["open_questions"]
                        log(f"Co-pilot updated the draft RFx: \"{msg[:80]}\"")
                    except LLMError as e:
                        st.error(str(e))
                st.rerun()
            if cp["history"] and st.button("Start over", icon=":material/restart_alt:", type="tertiary"):
                ss.copilot = dict(history=[], draft=None, open=[])
                st.rerun()
        with right:
            d = cp["draft"]
            with st.container(border=True, height=560):
                if not d:
                    md("<div class='eyebrow'>Live draft</div>")
                    md("<div class='muted'>The RFx builds here as you talk: lines, a must-pass questionnaire and commercial terms.</div>")
                else:
                    md("<div class='eyebrow'>Live draft</div>")
                    md(f"<div style='font-weight:650;font-size:1.15rem;line-height:1.35;margin:4px 0 6px 0'>{esc(d['title'])}</div>")
                    md(f"<div class='muted'>{esc(d['scope'])}</div>")
                    if cp["open"]:
                        st.warning("**Before sending**\n" + "\n".join(f"- {q}" for q in cp["open"]), icon=":material/help:")
                    st.markdown(f"**Lines** · {len(d['lines'])}")
                    st.dataframe(pd.DataFrame(d["lines"]), hide_index=True, width="stretch")
                    st.markdown(f"**Questionnaire** · {len(d['questionnaire'])}")
                    st.dataframe(pd.DataFrame(d["questionnaire"]), hide_index=True, width="stretch")
                    st.markdown("**Terms**")
                    md("<div class='kv'>" + "".join(f"<div class='k'>{esc(k.replace('_', ' ').capitalize())}</div><div>{esc(v)}</div>"
                                                    for k, v in d["terms"].items()) + "</div>")
            if d:
                if ss.issued_draft:
                    st.success("Issued. Replies will land in Responses.", icon=":material/send:")
                elif st.button("Review and send", type="primary", icon=":material/send:", width="stretch"):
                    send_dialog(d)
    with t2:
        terms = rfx["terms"]
        md(f"<div class='muted'>Issued {datetime.fromisoformat(rfx['issued']).strftime('%d %b %Y')} by {esc(rfx['buyer']['person'])} · "
           f"due {datetime.fromisoformat(rfx['due']).strftime('%d %b %Y')} · approver {esc(rfx['buyer']['approver'])}</div>")
        st.space("small")
        md("<div class='kv'>" + "".join(f"<div class='k'>{esc(k.replace('_', ' ').capitalize())}</div><div>{esc(v)}</div>"
                                        for k, v in terms.items()) + "</div>")
        st.space("small")
        st.dataframe(pd.DataFrame(rfx["lines"])[["id", "description", "ply", "flute", "size", "grade", "annual_qty", "weight_kg"]]
                     .rename(columns={"id": "Line", "description": "Item", "ply": "Ply", "flute": "Flute", "size": "Size",
                                      "grade": "Board grade", "annual_qty": "Qty / yr", "weight_kg": "Board kg / pc"}),
                     hide_index=True, width="stretch", height=300)
        st.markdown("**Questionnaire**")
        st.dataframe(pd.DataFrame(rfx["questionnaire"]).rename(columns={"id": "Q", "text": "Question", "must_pass": "Must pass", "rule": "Rule"}),
                     hide_index=True, width="stretch")
    next_link(P["responses"], "Next: Responses")


@st.dialog("Send the RFx")
def send_dialog(d):
    st.markdown(f"**{d['title']}**")
    # Approved vendors for the category always appear; co-pilot suggestions and buyer additions join them.
    master = [f"{x['name']} ({x['city']})" for x in rfx["vendors"].values()]
    known = " ".join(master).lower()
    suggested = [v for v in d.get("vendors_to_invite") or [] if v.strip() and v.split()[0].lower() not in known]
    ss.setdefault("extra_invites", [])
    st.markdown("**Approved packaging vendors**")
    picked = [v for v in master if st.checkbox(v, value=True, key=f"inv{v}")]
    if suggested or ss.extra_invites:
        st.markdown("**Suggested by the co-pilot or added by you**")
        picked += [v for v in suggested + ss.extra_invites if st.checkbox(v, value=True, key=f"inv{v}")]
    def add_invite():
        new = ss.get("new_invite", "").strip()
        if new and new not in ss.extra_invites:
            ss.extra_invites.append(new)
        ss.new_invite = ""
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    c1.text_input("Invite another vendor", placeholder="e.g. Mysore Packaging, Mysuru", key="new_invite")
    c2.button("Add", width="stretch", on_click=add_invite)
    st.caption(f"Each vendor gets the RFx and the template. They can reply in any format. Due date: {d['terms'].get('response_due', 'as stated')}.")
    if st.button(f"Send to {len(picked)} vendors", type="primary", disabled=not picked, width="stretch"):
        ss.issued_draft = True
        log(f"Issued draft RFx \"{d['title']}\" to {len(picked)} vendors: {'; '.join(picked)} (email simulated in this prototype).")
        st.rerun()


@st.dialog("Add a vendor reply", width="large")
def upload_dialog():
    st.caption("Drop in whatever the vendor sent: PDF, Excel, Word, a photo or pasted email text. The AI reads it live.")
    c1, c2 = st.columns([1, 2])
    target = c1.text_input("Vendor code", value="F", max_chars=2, help="A to E replaces that vendor's reply").strip().upper()
    vname = c2.text_input("Vendor name", placeholder="e.g. Mysore Packaging")
    ups = st.file_uploader("Quote files", accept_multiple_files=True)
    body = st.text_area("Email text (optional)", height=90)
    atts = st.file_uploader("Certificates or test reports (optional)", accept_multiple_files=True)
    ready = bool(target) and bool(ups or body.strip())
    if st.button("Read with AI", type="primary", disabled=not ready, width="stretch", icon=":material/auto_awesome:"):
        files = [(u.name, u.getvalue()) for u in (ups or [])]
        email = body.strip() or None
        if email and not files:
            files, email = [("email.txt", email.encode())], None
        with st.spinner("Reading the reply. This takes about a minute."):
            try:
                pipeline.run_vendor(rfx, target, ss.cache, files=files, email=email,
                                    atts=[(u.name, u.getvalue()) for u in (atts or [])], label=vname or f"Vendor {target}")
                ss.cache["meta"][target]["files"] = [n for n, _ in files]
                ss.inbox_sel = target
                log(f"Read a new reply from {vname or target} ({', '.join(n for n, _ in files)}).")
            except LLMError as e:
                st.error(str(e))
                return
        st.rerun()


def responses():
    ui.header("Step 2 · Collect", "Responses",
              "Every reply exactly as it arrived, next to what the AI read from it. Nobody re-typed anything.")
    vendors = sorted(set(DEMO_INBOX) | set(ss.cache["extractions"]))
    def caption(v):
        ex = ss.cache["extractions"].get(v)
        if not ex:
            return "Not read yet"
        flags = len(ex.get("red_flags", []))
        return f"{FORMAT.get(v, 'Uploaded')} · {len(ex['lines'])} prices" + (f" · {flags} notes" if flags else "")

    left, right = st.columns([1, 2.6], gap="large")
    with left:
        if st.button("Add a reply", icon=":material/upload_file:", width="stretch", type="primary"):
            upload_dialog()
        st.space("small")
        sel = st.radio("Inbox", vendors, format_func=short, captions=[caption(v) for v in vendors], key="inbox_sel",
                       label_visibility="collapsed")
        st.space("small")
        with st.popover("Re-read all", icon=":material/refresh:", width="stretch"):
            st.caption("Sends all five original replies to the model again, live. Takes 3 to 5 minutes.")
            if st.button("Re-read all five now", type="primary"):
                prog = st.progress(0.0, text="Reading...")
                for i, v in enumerate(DEMO_INBOX):
                    try:
                        pipeline.run_vendor(rfx, v, ss.cache)
                        log(f"Re-read {short(v)} live.")
                    except LLMError as e:
                        st.error(f"{v}: {e}")
                    prog.progress((i + 1) / len(DEMO_INBOX), text=f"Read {short(v)}")
                st.rerun()
    v = sel
    ex = ss.cache["extractions"].get(v)
    meta = ss.cache["meta"].get(v, {})
    with right:
        h1, h2 = st.columns([3, 1], vertical_alignment="center")
        name = (ex or {}).get("vendor_name") or rfx["vendors"].get(v, {}).get("name", v)
        city = rfx["vendors"].get(v, {}).get("city", "")
        h1.subheader(name, anchor=False)
        h1.caption(" · ".join(x for x in [city, "incumbent" if v == rfx["incumbent"] else "", FORMAT.get(v, "")] if x))
        if v in DEMO_INBOX and h2.button("Re-read with AI", icon=":material/auto_awesome:", key=f"run{v}", width="stretch"):
            with st.spinner("Reading the original files. About a minute."):
                try:
                    pipeline.run_vendor(rfx, v, ss.cache)
                    log(f"Re-read {short(v)} live.")
                except LLMError as e:
                    st.error(str(e))
            st.rerun()
        tabs = st.tabs(["What they sent", "What the AI read", "Certificates"])
        with tabs[0]:
            spec = DEMO_INBOX.get(v, {})
            if spec.get("email"):
                md(f"<div class='quote'>{esc(spec['email'])}</div>")
            for f in meta.get("files") or spec.get("files", []):
                p = INBOX / f
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1], vertical_alignment="center")
                    c1.markdown(f":material/description: **{f}**")
                    if not p.exists():
                        c1.caption("Uploaded in this session")
                        continue
                    c2.download_button("Download", p.read_bytes(), file_name=f, key=f"dl{v}{f}", icon=":material/download:", type="tertiary")
                    if p.suffix.lower() in (".jpg", ".png"):
                        st.image(str(p), width=520)
                    elif p.suffix == ".txt":
                        md(f"<div class='quote' style='white-space:pre-wrap'>{esc(p.read_text(encoding='utf-8'))}</div>")
                    elif p.suffix == ".docx":
                        with st.container(height=420, border=False):
                            md(f"<div class='quote' style='white-space:pre-wrap'>{esc(docx_text(str(p)))}</div>")
                    elif p.suffix == ".xlsx":
                        st.dataframe(xlsx_frame(str(p)), hide_index=True, width="stretch", height=420)
                    elif p.suffix == ".pdf":
                        for img in pdf_pages(str(p)):
                            st.image(img, width="stretch")
        with tabs[1]:
            if not ex:
                st.info("Not read yet. Use **Re-read with AI**.")
            else:
                md(f"<div style='font-size:0.95rem;line-height:1.55'>{esc(ex['summary'])}</div>")
                if meta.get("seconds"):
                    st.caption(f"Read in {meta['seconds']:.0f} s · {meta.get('input_tokens', 0):,} tokens in, {meta.get('output_tokens', 0):,} out")
                t = ex["terms"]
                md("<div class='kv' style='margin:10px 0 14px 0'>" + "".join(
                    f"<div class='k'>{k}</div><div>{esc(val) if val not in (None, '') else '–'}</div>" for k, val in [
                        ("Delivery", t.get("delivery")), ("Freight", t.get("freight")), ("Payment", f"{t['payment_days']} days" if t.get("payment_days") else None),
                        ("Validity", t.get("validity")), ("Lead time", f"{t['lead_time_days']} days" if t.get("lead_time_days") else None),
                        ("GST", t.get("gst_treatment")), ("Not quoted", ", ".join(ex["unquoted_rfx_lines"]) or "none")]) + "</div>")
                if ex["red_flags"]:
                    st.markdown("**What needs attention**")
                    md("".join(f"<div class='flag'>⚠ {esc(f)}</div>" for f in ex["red_flags"]))
                with st.expander(f"Every price it found ({len(ex['lines'])})"):
                    st.dataframe(pd.DataFrame([dict(Line=q["rfx_line_id"], **{"Vendor wrote": q["evidence_quote"]}, Value=q["price_value"],
                                                    Unit=q["price_unit"], Currency=q["currency"], Where=q["evidence_location"],
                                                    Confidence=q["extraction_confidence"]) for q in ex["lines"]]),
                                 hide_index=True, width="stretch",
                                 column_config={"Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
        with tabs[2]:
            atts = ss.cache["attachments"].get(v, [])
            if not atts:
                st.caption("No certificates or test reports were attached.")
            for a_ in atts:
                expired = a_.get("valid_until") and a_["valid_until"] < "2026-10-12"
                with st.container(border=True):
                    md(f"<b>{esc(a_['doc_type'].replace('_', ' ').capitalize())}</b> · <span class='muted'>{esc(a_['file'])}</span> "
                       + (ui.tag("Expired " + a_["valid_until"], "#FDECE8", "#B4321B") if expired else
                          ui.tag("Valid to " + a_["valid_until"], "#E8F5EC", "#1C6B38") if a_.get("valid_until") else ""))
                    md(f"<div class='muted' style='margin-top:6px'>{esc(a_['key_facts'])}</div>")
    next_link(P["compare"], "Next: Compare")


def compare():
    ui.header("Step 3 · Compare", "One comparison, like for like",
              "Same 30 lines, per piece, rupees, ex-GST. Click any price to see the exact words it came from and every conversion applied.")
    if need_data():
        return
    vinfo = comp["vendors"]
    vcodes = sorted(vinfo)
    c1, c2, c3 = st.columns([1.3, 2.2, 1.6], vertical_alignment="bottom")
    basis = c1.segmented_control("Price basis", ["Landed", "As quoted"], default="Landed", key="basis",
                                 help="Landed adds the assumed freight where a vendor said 'freight extra'.") or "Landed"
    groups = {"All": None, "3-ply": 3, "5-ply": 5, "7-ply": 7, "Partitions & pads": 0}
    grp = c2.segmented_control("Lines", list(groups), default="All", key="grp") or "All"
    trusted_only = c3.toggle("Best price from trusted only", value=True, help="Ignore inferred and needs-review prices when marking the best")
    key = "landed" if basis == "Landed" else "value"
    ui.legend("★ best price on the line")

    sel_lines = [l for l in rfx["lines"] if groups[grp] is None or (l["ply"] == groups[grp] if groups[grp] else l["kind"] != "RSC")]
    rows, styles = [], []
    for l in sel_lines:
        lyp = float(ly[l["id"]]["price_inr_per_pc_ex_gst"])
        r = {"Line": l["id"], "Item": l["description"], "Spec": f"{l['ply']}-ply {l['flute']}" if l["kind"] == "RSC" else l["kind"].capitalize(),
             "Qty / yr": f"{l['annual_qty']:,}", "Last yr": f"{lyp:.2f}"}
        cells = {v: comp["cells"][(v, l["id"])] for v in vcodes}
        ok = {v: c[key] for v, c in cells.items() if c[key] is not None and (not trusted_only or c["status"] in TRUSTED)}
        best_v = min(ok, key=ok.get) if ok else None
        srow = {}
        for v, c in cells.items():
            r[gname(v)] = "–" if c[key] is None else (f"★ {c[key]:.2f}" if v == best_v else f"{c[key]:.2f}")
            _, bg, fg, _ = STATUS[c["status"]]
            srow[gname(v)] = f"background-color:{bg};color:{fg}" + (";font-weight:700" if v == best_v else "")
        r["Best vs last yr"] = f"{short(best_v).split()[0]} {(ok[best_v] / lyp - 1) * 100:+.1f}%" if best_v else "–"
        rows.append(r); styles.append(srow)
    df = pd.DataFrame(rows)
    sty = pd.DataFrame("", index=df.index, columns=df.columns)
    for i, srow in enumerate(styles):
        for col, s_ in srow.items():
            sty.loc[i, col] = s_
    event = st.dataframe(df.style.apply(lambda _: sty, axis=None), hide_index=True, width="stretch",
                         height=min(36 * (len(df) + 1) + 4, 760), on_select="rerun", selection_mode="single-cell", key="grid",
                         column_config={"Line": st.column_config.TextColumn(width=48), "Item": st.column_config.TextColumn(width=170),
                                        "Spec": st.column_config.TextColumn(width=72), "Qty / yr": st.column_config.TextColumn(width=72),
                                        "Last yr": st.column_config.TextColumn(width=58),
                                        **{gname(v): st.column_config.TextColumn(width=84) for v in vcodes},
                                        "Best vs last yr": st.column_config.TextColumn(width=110)})

    # ---- cell inspector: driven by the grid click, with pickers as a fallback
    picked = event.selection.cells if event and event.selection else []
    if picked:
        row_i, col = picked[0]
        by_short = {gname(v): v for v in vcodes}
        if col in by_short and row_i < len(df):
            new = (by_short[col], df.iloc[row_i]["Line"])
            if ss.get("last_pick") != new:
                ss.last_pick = new
                ss.insp_v, ss.insp_l = new
    with st.container(border=True):
        md("<div class='eyebrow'>Trace a price</div>")
        p1, p2 = st.columns(2)
        iv = p1.selectbox("Vendor", vcodes, format_func=short, key="insp_v")
        il = p2.selectbox("Line", list(LINES), format_func=lambda i: f"{i} · {LINES[i]['description']}", key="insp_l")
        c = comp["cells"][(iv, il)]
        q = c["q"]
        a, b = st.columns([1.3, 1], gap="large")
        with a:
            md(f"{ui.pill(c['status'])} &nbsp;<span class='muted'>{STATUS[c['status']][3]}</span>")
            if q:
                md(f"<div class='quote'>“{esc(q['evidence_quote'])}”</div><div class='muted'>{esc(q['evidence_location'])}</div>")
                st.space("small")
                md("<div class='kv'>"
                   f"<div class='k'>Read as</div><div>{esc(q['price_value'])} {esc(q['currency'])} · {esc(q['unit_text'] or q['price_unit'])}"
                   f"{' · incl. GST' if q['gst_inclusive'] else ''}</div>"
                   f"<div class='k'>Per piece, ex-GST</div><div><b>{money(c['value'])}</b></div>"
                   f"<div class='k'>Landed</div><div>{money(c['landed'])}</div>"
                   f"<div class='k'>Confidence</div><div>reading {q['extraction_confidence']:.2f} · line match {q['match_confidence']:.2f}</div>"
                   "</div>")
            else:
                st.caption("This vendor did not quote this line.")
        with b:
            if c["tags"]:
                st.markdown("**How the number was made**")
                md("".join(f"<div class='flag'>→ {esc(t)}</div>" for t in c["tags"]))
            if c["reasons"]:
                st.markdown("**Why it is held**")
                md("".join(f"<div class='flag'>⚠ {esc(r_)}</div>" for r_ in c["reasons"]))
            if c["status"] in ("review", "inferred"):
                st.page_link(P["resolve"], label="Resolve this in the review queue", icon=":material/arrow_forward:")
        src = [f for f in (ss.cache["meta"].get(iv, {}).get("files") or DEMO_INBOX.get(iv, {}).get("files", []))
               if f.lower().endswith((".jpg", ".png"))]
        if q and src and (INBOX / src[0]).exists():
            with st.expander("Show the source photo"):
                st.image(str(INBOX / src[0]), width=620)

    st.subheader("Vendors", anchor=False)
    cols = st.columns(len(vcodes))
    vt = []
    for col, v in zip(cols, vcodes):
        x = vinfo[v]
        tot = sum((comp["cells"][(v, l)][key] or 0) * LINES[l]["annual_qty"] for l in LINES)
        n_open = sum(1 for l in LINES if comp["cells"][(v, l)]["status"] in ("review", "inferred"))
        vt.append({"Vendor": x["name"], "Lines quoted": x["coverage"], "Qualification": x["qualification"]["status"],
                   "Why": "; ".join(x["qualification"]["reasons"]), "Capacity t/month": x["capacity_t_month"],
                   "Payment days": x["terms"].get("payment_days"), "Freight": x["terms"].get("freight"), "Value of quoted lines": round(tot),
                   "Open items": n_open})
        with col.container(border=True):
            md(f"<div class='vcard'><div class='name'>{esc(short(v))}</div>"
               f"<div class='meta'>{x['coverage']}/30 lines · {esc(x['terms'].get('payment_days') or '–')} days · freight {esc(x['terms'].get('freight') or '–')}</div>"
               f"<div class='big'>{inr(tot)}</div><div class='muted small' style='margin-bottom:8px'>quoted lines, {basis.lower()}</div>"
               f"{ui.qual_tag(x['qualification']['status'])}" + (f" {ui.pill('review', str(n_open) + ' open')}" if n_open else "") + "</div>")
            notes = x["qualification"]["reasons"] + x["flags"]
            if notes:
                with st.popover(f"{len(notes)} notes", width="stretch"):
                    md("".join(f"<div class='flag'>{esc(n)}</div>" for n in notes))
    if comp["alternates"]:
        with st.expander(f"Alternate offers kept out of the comparison ({len(comp['alternates'])})"):
            st.caption("Not like-for-like with the RFx spec, so they never compete with compliant prices.")
            st.dataframe(pd.DataFrame(comp["alternates"]), hide_index=True, width="stretch")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="comparison", index=False)
        pd.DataFrame(vt).to_excel(w, sheet_name="vendors", index=False)
        pd.DataFrame([dict(vendor=v_, line=l_, status=c_["status"], price=c_["value"], landed=c_["landed"],
                           how="; ".join(c_["tags"]), review="; ".join(c_["reasons"]),
                           source=(c_["q"] or {}).get("evidence_quote")) for (v_, l_), c_ in comp["cells"].items()]
                     ).to_excel(w, sheet_name="audit_trail", index=False)
    st.space("small")
    e1, e2 = st.columns([3, 1])
    e1.download_button("Export to Excel, with audit trail", buf.getvalue(), file_name=f"{rfx['id']}_comparison.xlsx",
                       icon=":material/download:", on_click=lambda: log("Exported the comparison with audit trail."))
    e2.page_link(P["resolve"], label="Next: Resolve", icon=":material/arrow_forward:", width="stretch")


def resolve():
    ui.header("Step 4 · Resolve", "Review queue",
              "These prices are held out of every award until you look. Confirm the value, correct it, or ask the vendor in one email.")
    if need_data():
        return
    items = open_items(comp)
    done = len(ss.overrides)
    total = done + len(items)
    st.progress(done / total if total else 1.0, text=f"{done} of {total} resolved")

    vendors = sorted({c["vendor"] for c in items} | {v for v, x in comp["vendors"].items() if x["qualification"]["status"] != "pass"})
    if not vendors:
        st.success("Nothing open. Every price in the comparison is trusted.", icon=":material/task_alt:")
    count = {v: sum(1 for c in items if c["vendor"] == v) for v in vendors}
    load = {v: count[v] + sum(1 for k in ss.overrides if k.startswith(v + "|")) for v in vendors}
    vendors.sort(key=lambda v: (-load[v], v))  # stable order: tabs don't jump as items are resolved
    tabs = st.tabs([f"{short(v)} · {count[v]}" if count[v] else f"{short(v)} · qualification" for v in vendors]) if vendors else []
    for tab, v in zip(tabs, vendors):
        with tab:
            x = comp["vendors"][v]
            vi = sorted([c for c in items if c["vendor"] == v], key=lambda c: c["line"])
            asked = ss.asks.setdefault(v, [])
            if x["qualification"]["status"] != "pass":
                md(f"<div class='next' style='background:#FDF7EC;border-color:#F3E3BF'><div class='t'>{ui.qual_tag(x['qualification']['status'])} "
                   f"&nbsp;Qualification</div><div class='d'>" + "<br>".join(esc(r_) for r_ in x["qualification"]["reasons"]) + "</div></div>")
            if vi:
                h1, h2 = st.columns([3, 1], vertical_alignment="center")
                h1.caption(f"{len(vi)} prices from {short(v)} need a decision.")
                with h2.popover("Accept all as shown", width="stretch"):
                    st.caption(f"Marks all {len(vi)} as confirmed at the value shown. Use only if you have checked them.")
                    if st.button("Confirm all", type="primary", key=f"all{v}"):
                        for c in vi:
                            ss.overrides[f"{v}|{c['line']}"] = dict(value=c["value"], note=f"accepted at ₹{c['value']:.2f} (bulk)")
                        log(f"Accepted all {len(vi)} open prices from {short(v)} as shown.")
                        st.rerun()
            for c in vi:
                q = c["q"] or {}
                with st.container(border=True):
                    a, b = st.columns([2.2, 1], gap="large")
                    with a:
                        md(f"<b>{c['line']} · {esc(LINES[c['line']]['description'])}</b> &nbsp;{ui.pill(c['status'])}"
                           + (f" {ui.tag('In email', '#E9F0FD', '#1F4FB8')}" if c["line"] in asked else ""))
                        if q.get("evidence_quote"):
                            md(f"<div class='quote'>“{esc(q['evidence_quote'])}”</div>")
                        why = c["reasons"] + [t for t in c["tags"] if "last year" in t or "interpreted" in t]
                        md("".join(f"<div class='muted small'>⚠ {esc(w)}</div>" for w in dict.fromkeys(why)))
                    with b:
                        newv = st.number_input("Price to use, ₹/pc ex-GST", value=float(round(c["value"] or 0.0, 2)), step=0.01,
                                               key=f"nv{v}{c['line']}", format="%.2f")
                        b1, b2 = st.columns(2)
                        if b1.button("Confirm", key=f"ok{v}{c['line']}", type="primary", width="stretch"):
                            ss.overrides[f"{v}|{c['line']}"] = dict(value=newv, note=f"confirmed at ₹{newv:.2f}")
                            changed = c["value"] is None or abs(newv - c["value"]) > 0.005
                            log(f"{'Corrected' if changed else 'Confirmed'} {short(v)} {c['line']} at ₹{newv:.2f}"
                                + (f" (system had ₹{c['value']:.2f})" if changed and c["value"] is not None else "") + ".")
                            st.rerun()
                        if c["line"] in asked:
                            if b2.button("Remove", key=f"un{v}{c['line']}", width="stretch"):
                                asked.remove(c["line"]); st.rerun()
                        elif b2.button("Ask vendor", key=f"ask{v}{c['line']}", width="stretch"):
                            asked.append(c["line"])
                            log(f"Added {short(v)} {c['line']} to the clarification email.")
                            st.rerun()

            # ---- one email per vendor
            ask_cells = [c for c in vi if c["line"] in asked] or vi
            issues = []
            for c in ask_cells:
                q = c["q"] or {}
                issues.append(f"Line {c['line']} ({LINES[c['line']]['description']}): we read '{q.get('evidence_quote', '')}'. "
                              f"Open point: {'; '.join(c['reasons'][:2]) or 'price not restated, we assumed last year'}")
            issues += [f"Questionnaire {r_}" for r_ in x["qualification"]["reasons"]]
            if x["freight_extra"]:
                issues.append("Freight: how is it charged (per trip, per kg, % of value) to the Bidadi plant?")
            st.space("small")
            with st.container(border=True):
                e1, e2 = st.columns([3, 1.2], vertical_alignment="center")
                scope = [f"{len(ask_cells)} price{'s' if len(ask_cells) != 1 else ''}" if ask_cells else None,
                         f"{len(x['qualification']['reasons'])} qualification point{'s' if len(x['qualification']['reasons']) != 1 else ''}"
                         if x["qualification"]["reasons"] else None, "freight" if x["freight_extra"] else None]
                e1.markdown(f"**One clarification email to {short(v)}**")
                e1.caption("Covers " + ", ".join(s_ for s_ in scope if s_) + "."
                           + ("" if any(c["line"] in asked for c in vi) or not vi else " No prices marked, so it asks about every open one."))
                if e2.button("Draft email", key=f"mail{v}", icon=":material/edit:", width="stretch", disabled=not issues):
                    with st.spinner("Drafting..."):
                        try:
                            ss.mails[v] = copilot.clarification_email(rfx, x["name"], issues)
                            ss.sent.pop(v, None)
                            log(f"Drafted a clarification email to {short(v)} ({len(issues)} points).")
                        except LLMError as e:
                            st.error(str(e))
                m = ss.mails.get(v)
                if m:
                    st.text_input("Subject", m["subject"], key=f"sub{v}")
                    st.text_area("Message", m["body"], height=260, key=f"body{v}")
                    if ss.sent.get(v):
                        st.success(f"Sent to {x['name']} at {ss.sent[v]}. Their answer comes back through Responses.", icon=":material/mark_email_read:")
                    elif st.button("Send", key=f"send{v}", type="primary", icon=":material/send:"):
                        ss.sent[v] = datetime.now().strftime("%H:%M")
                        log(f"Sent the clarification email to {short(v)} (simulated).")
                        st.rerun()

    if ss.overrides:
        with st.expander(f"Resolved ({len(ss.overrides)})"):
            for k, o in list(ss.overrides.items()):
                v, l = k.split("|")
                r1, r2 = st.columns([5, 1], vertical_alignment="center")
                r1.markdown(f"{short(v)} · **{l}** {LINES[l]['description']} · {o['note']}")
                if r2.button("Undo", key=f"undo{k}", type="tertiary"):
                    del ss.overrides[k]
                    log(f"Undid the decision on {short(v)} {l}.")
                    st.rerun()
    next_link(P["decide"], "Next: Decide")


def scenario_view(r, key):
    m1, m2, m3 = st.columns(3)
    m1.metric("Annual cost", inr(r["total_inr"]), f"{r['change_vs_last_year_pct']:+.2f}% vs last year" if r["change_vs_last_year_pct"] is not None else None,
              delta_color="inverse")
    m2.metric("Lines awarded", f"{r['lines_awarded']} of 30")
    m3.metric("Vendors", len(r["share"]))
    if r["share"]:
        sh = pd.DataFrame([dict(vendor=k, pct=v_["pct"], value=v_["value"]) for k, v_ in r["share"].items()])
        fig = px.bar(sh, x="pct", y="vendor", orientation="h", text=sh["pct"].map(lambda p: f"{p:.0f}%"),
                     color_discrete_sequence=["#3D4FE0"])
        fig.update_layout(height=60 + 34 * len(sh), margin=dict(l=0, r=0, t=0, b=0), xaxis_title=None, yaxis_title=None,
                          xaxis=dict(visible=False, range=[0, 105]), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", key=f"sh{key}", config={"displayModeBar": False})
    for w_ in r["warnings"]:
        st.warning(w_, icon=":material/warning:")
    for m_ in r.get("cap_moves", []):
        st.caption(m_)
    rows = pd.DataFrame(r["rows"])
    with st.expander("Line-by-line award"):
        st.dataframe(rows, hide_index=True, width="stretch")
    buf = io.BytesIO(); rows.to_excel(buf, index=False)
    st.download_button("Download award (Excel)", buf.getvalue(), file_name=f"award_{key}.xlsx", key=f"x{key}",
                       icon=":material/download:", type="tertiary")


def decide():
    ui.header("Step 5 · Decide", "Decide the award",
              "Three award options computed by code from trusted prices only. Then ask the analyst anything, in plain words.")
    if need_data():
        return
    items = open_items(comp)
    if items:
        i1, i2 = st.columns([4, 1], vertical_alignment="center")
        i1.info(f"{len(items)} prices are still open, so they are left out of these options until you resolve them.", icon=":material/info:")
        i2.page_link(P["resolve"], label="Resolve", icon=":material/arrow_forward:", width="stretch")

    single = []
    for v, x in comp["vendors"].items():
        if x["qualification"]["status"] == "pass":
            r = optimizer.award(comp, rfx, ly, single_vendor=v)
            if not r["lines_unawarded"]:
                single.append(r)
    options = [
        ("rec", "Split among qualified vendors", "Cheapest trusted price per line, only vendors who passed every must-pass check.",
         optimizer.award(comp, rfx, ly, qualified_only=True)),
        ("low", "Lowest price, any vendor", "Ignores qualification. Shows what cutting corners would save, and the risk.",
         optimizer.award(comp, rfx, ly)),
    ]
    if single:
        s = min(single, key=lambda r: r["total_inr"])
        options.append(("one", f"Single source: {short(s['rows'][0]['vendor'])}", "One qualified vendor covering all 30 lines. Simplest to run.", s))
    cols = st.columns(len(options))
    for col, (k, title, desc, r) in zip(cols, options):
        with col.container(border=True, height="stretch"):
            chosen = ss.award_choice == title
            md(f"<div class='eyebrow'>{'Recommended' if k == 'rec' else 'Option'}</div><div class='vcard'><div class='name'>{esc(title)}</div>"
               f"<div class='meta'>{esc(desc)}</div><div class='big'>{inr(r['total_inr'])}</div>"
               f"<div class='muted small'>{r['change_vs_last_year_pct']:+.2f}% vs last year · "
               + " · ".join(f"{esc(n.split()[0])} {s_['pct']:.0f}%" for n, s_ in r["share"].items()) + "</div></div>")
            st.space("small")
            if r["warnings"]:
                with st.popover(f"{len(r['warnings'])} risk{'s' if len(r['warnings']) != 1 else ''}", icon=":material/warning:", width="stretch"):
                    md("".join(f"<div class='flag'>{esc(w)}</div>" for w in r["warnings"]))
            else:
                md(f"{ui.tag('No risks flagged', '#E8F5EC', '#1C6B38')}")
                st.space("small")
            if chosen:
                st.button("Recommended", key=f"ch{k}", disabled=True, icon=":material/check:", width="stretch")
            elif st.button("Recommend this", key=f"ch{k}", type="primary" if k == "rec" else "secondary", width="stretch"):
                ss.award_choice = title
                log(f"Recommended award: {title}, {inr(r['total_inr'])} ({r['change_vs_last_year_pct']:+.2f}% vs last year).", kind="decision")
                st.toast("Recommendation recorded in the audit trail", icon=":material/check_circle:")
                st.rerun()
            with st.expander("Details"):
                scenario_view(r, k)

    st.space("medium")
    h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
    h1.subheader("Ask the analyst", anchor=False)
    h1.caption("It answers with SQL and the award engine, never from memory, and shows its working.")
    if ss.chat and h2.button("Clear chat", icon=":material/delete_sweep:", type="tertiary", width="stretch"):
        ss.chat = []
        ss.pop("analyst", None)
        st.rerun()
    build_args = dict(assumptions=ss.assumptions, extractions=ss.cache["extractions"], attachments=ss.cache["attachments"],
                      overrides=overrides_tuple())
    if "analyst" not in ss:
        ss.analyst = analyst_mod.Analyst(comp, rfx, ly, build_args)
    ss.analyst.build_args = build_args
    ss.analyst.set_comp(comp)

    sugg = ["Which vendors quoted all 30 lines, and what is missing from the others?",
            "How confident are we in Sri Lakshmi's prices?",
            "What if we split it, cheapest per line, but only among vendors who cleared the quality questionnaire?",
            "Cap any single vendor at 60% of spend. What does that cost us?",
            "What happens to the award if the rupee weakens to 92 per dollar?",
            "Compare the split with giving everything to one vendor. Show a chart.",
            "Write the award recommendation memo for my VP."]

    def take_sugg():
        ss.pending_q = ss.sugg
        ss.sugg = None

    st.pills("Try asking", sugg, key="sugg", on_change=take_sugg, label_visibility="collapsed")

    def render(arts, base):
        for j, (kind, title, obj) in enumerate(arts):
            if kind == "table":
                with st.expander(f"Query · {title}", icon=":material/database:"):
                    st.dataframe(obj, hide_index=True, width="stretch")
            elif kind == "chart":
                obj.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(obj, width="stretch", key=f"c{base}_{j}")
            elif kind == "scenario":
                with st.expander(f"Scenario · {title} · {inr(obj['total_inr'])}", icon=":material/calculate:"):
                    scenario_view(obj, f"{base}_{j}")
            elif kind == "memo":
                st.download_button(f"Download memo: {title}", obj.encode(), file_name="award_memo.md", key=f"m{base}_{j}",
                                   icon=":material/description:", on_click=lambda: log("Downloaded the award memo.", kind="decision"))

    for i, (role, text, arts) in enumerate(ss.chat):
        with st.chat_message(role, avatar=":material/person:" if role == "user" else ":material/insights:"):
            st.markdown(text)
            render(arts, i)
    q = st.chat_input("Ask anything about the quotes", key="an_in") or ss.pop("pending_q", None)
    if q:
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(q)
        with st.chat_message("assistant", avatar=":material/insights:"):
            steps = st.status("Working through the data...", expanded=False)
            try:
                ans, arts = ss.analyst.ask(q, on_step=lambda s_: steps.write(s_))
                steps.update(label=f"Done · {len(arts)} step{'s' if len(arts) != 1 else ''}", state="complete")
            except LLMError as e:
                ans, arts = f"Something went wrong: {e}", []
                steps.update(label="Failed", state="error")
            st.markdown(ans)
            render(arts, len(ss.chat) + 1)
        ss.chat += [("user", q, []), ("assistant", ans, arts)]
        log(f"Asked the analyst: \"{q}\"")
    next_link(P["audit"], "Next: Audit trail")


def accuracy():
    ui.header("Assurance", "How accurate is the reader?",
              "The test data was built by hand, so the right answer for every cell is known. This scores the current read "
              "and checks that the review queue catches what the AI gets wrong. Your edits are excluded.")
    if need_data():
        return
    clean = normalize.build(rfx, ly, ss.cache["extractions"], ss.cache["attachments"], rfx["assumptions"], {})
    key_ = load_answer_key()
    rows = scorecard.score(clean, key_)
    summ = scorecard.summary(rows)
    tot = sum(b["n"] for b in summ.values()); cor = sum(b["correct"] for b in summ.values())
    silent = sum(b["silent_wrong"] for b in summ.values()); caught = sum(b["caught"] for b in summ.values())
    held = sum(1 for r in rows if r["outcome"] == "correct, held for review")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cells read correctly", f"{cor}/{tot}", help=f"{cor / tot * 100:.1f}% within 1% of the true per-piece price" if tot else None, border=True)
    m2.metric("Correct, but held for you", held, help="Right answer, but the system was unsure, so a person checks it", border=True)
    m3.metric("Wrong, caught by the queue", caught, border=True)
    m4.metric("Wrong and trusted", silent, help="The number that matters most. Should be zero.", border=True)
    st.space("small")
    df = pd.DataFrame([dict(Vendor=short(v), Format=FORMAT.get(v, key_["vendors"][v]["format"]), Cells=b["n"],
                            Correct=b["correct"] / b["n"], **{"Caught by queue": b["caught"], "Wrong and trusted": b["silent_wrong"]})
                       for v, b in summ.items()])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Correct": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
    bad = [r for r in rows if r["outcome"] not in ("correct", "correctly not quoted")]
    if bad:
        with st.expander(f"Every cell that was not a clean pass ({len(bad)})"):
            st.dataframe(pd.DataFrame(bad), hide_index=True, width="stretch")
    ui.footer()


def audit():
    ui.header("Assurance", "Audit trail", "Everything decided in this session, in order. This is what goes in the award file.")
    if ss.award_choice:
        st.success(f"Recommendation: **{ss.award_choice}**", icon=":material/gavel:")
    if not ss.log:
        st.caption("Nothing yet. Actions you take on any page appear here.")
    else:
        df = pd.DataFrame(ss.log)[["time", "kind", "msg"]].assign(kind=lambda d: d["kind"].str.capitalize()).rename(columns={"time": "Time", "kind": "Type", "msg": "What happened"})
        st.dataframe(df, hide_index=True, width="stretch", column_config={"What happened": st.column_config.TextColumn(width="large")})
        st.download_button("Download audit trail (CSV)", df.to_csv(index=False).encode(), file_name=f"{rfx['id']}_audit_trail.csv",
                           icon=":material/download:")
    if ss.overrides:
        st.subheader("Prices you confirmed or corrected", anchor=False)
        st.dataframe(pd.DataFrame([dict(Vendor=short(k.split("|")[0]), Line=k.split("|")[1], Value=round(o["value"], 2), Note=o["note"])
                                   for k, o in ss.overrides.items()]), hide_index=True, width="stretch")
    ui.footer()


# ================================================================== navigation + sidebar
P = {
    "overview": st.Page(overview, title="Overview", icon=":material/space_dashboard:", default=True),
    "draft": st.Page(draft, title="Draft RFx", icon=":material/edit_note:", url_path="draft"),
    "responses": st.Page(responses, title="Responses", icon=":material/inbox:", url_path="responses"),
    "compare": st.Page(compare, title="Compare", icon=":material/table_chart:", url_path="compare"),
    "resolve": st.Page(resolve, title="Resolve", icon=":material/task_alt:", url_path="resolve"),
    "decide": st.Page(decide, title="Decide", icon=":material/gavel:", url_path="decide"),
    "accuracy": st.Page(accuracy, title="Accuracy", icon=":material/verified:", url_path="accuracy"),
    "audit": st.Page(audit, title="Audit trail", icon=":material/history:", url_path="audit"),
}
nav = st.navigation({"": [P["overview"]],
                     "Sourcing event": [P["draft"], P["responses"], P["compare"], P["resolve"], P["decide"]],
                     "Assurance": [P["accuracy"], P["audit"]]})

ASSETS = Path(__file__).resolve().parent / "assets"
st.logo(str(ASSETS / "logo.svg"), size="large", icon_image=str(ASSETS / "icon.svg"))
with st.sidebar:
    md(f"<div class='event'><div class='id'>{rfx['id']}</div><div class='tt'>Corrugated packaging, FY 2026-27</div></div>")
    st.space("small")
    with st.expander("Assumptions", icon=":material/tune:"):
        st.caption("Change any of these and every price, total and award recomputes.")
        a = ss.assumptions
        a["fx_usd_inr"] = st.number_input("USD to INR", value=float(a["fx_usd_inr"]), step=0.5)
        a["freight_pct_if_extra"] = st.number_input("Freight % when 'extra'", value=float(a["freight_pct_if_extra"]), step=0.5)
        a["gst_pct"] = st.number_input("GST % on inclusive quotes", value=float(a["gst_pct"]), step=1.0)
    with st.popover("Reset demo", icon=":material/restart_alt:", width="stretch"):
        st.caption("Restores the original replies and clears your decisions, emails and chat.")
        if st.button("Reset everything", type="primary"):
            if SEED.exists():
                shutil.copy(SEED, pipeline.CACHE)
            for k in list(ss.keys()):
                del ss[k]
            st.rerun()
    md("<div class='who'><div class='av'>AR</div><div><div class='nm'>Ananya Rao</div><div class='rl'>Category Buyer, Packaging</div></div></div>")

comp = build_comp()  # assumptions may have changed in the sidebar
nav.run()

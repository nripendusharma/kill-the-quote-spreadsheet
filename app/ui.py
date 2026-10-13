"""Look and feel: one stylesheet and a handful of small HTML components, so pages stay readable."""
import html

import streamlit as st

STATUS = {  # key: (label, background, text, one-line meaning)
    "verified": ("Verified", "#E8F5EC", "#1C6B38", "Read directly from the reply, high confidence"),
    "converted": ("Converted", "#E9F0FD", "#1F4FB8", "Unit, currency or tax converted by code"),
    "buyer_confirmed": ("Confirmed", "#F1ECFD", "#5B34C4", "Checked and confirmed by you"),
    "inferred": ("Inferred", "#FDF4DC", "#8A5A00", "Not restated by vendor, filled from last year"),
    "review": ("Needs review", "#FDECE8", "#B4321B", "Low confidence or failed a check"),
    "not_quoted": ("Not quoted", "#F2F2F0", "#77736B", "No price for this line"),
}
TRUSTED = ("verified", "converted", "buyer_confirmed")

CSS = """
<style>
:root { --ink:#16161A; --muted:#6B6A66; --line:#E7E5E0; --card:#FFFFFF; --accent:#3D4FE0; --soft:#F6F5F2; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], #MainMenu, footer { display: none; }
[data-testid="stSidebar"] { border-right: 1px solid var(--line); }
[data-testid="stSidebarNav"] a span { font-size: 0.93rem; }
h1 { font-weight: 650 !important; letter-spacing: -0.02em; font-size: 1.85rem !important; padding-bottom: 0.45rem !important; }
h3 { font-weight: 620 !important; letter-spacing: -0.01em; }
[data-testid="stMetric"] { background: var(--card); }
[data-testid="stMetricValue"] { font-weight: 640; letter-spacing: -0.02em; }
.stTabs [data-baseweb="tab-list"] { gap: 1.4rem; }
.stTabs [data-baseweb="tab"] { padding-left: 0; padding-right: 0; }

.eyebrow { font-size: 0.74rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin-bottom: 0.15rem; }
.sub { color: var(--muted); font-size: 1rem; margin: 0.35rem 0 1.6rem 0; max-width: 780px; line-height: 1.5; }
.muted { color: var(--muted); font-size: 0.86rem; line-height: 1.5; }
.small { font-size: 0.82rem; }

.pill { display:inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.74rem; font-weight: 600; line-height: 1.6; white-space: nowrap; }
.legend { display:flex; flex-wrap:wrap; gap: 6px 14px; align-items:center; margin: 0.2rem 0 0.7rem 0; }
.legend span.note { color: var(--muted); font-size: 0.78rem; }

.steps { display:grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 0.4rem 0 1.4rem 0; }
.step { border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; background: var(--card); }
.step .n { font-size: 0.72rem; font-weight: 600; color: var(--muted); letter-spacing: 0.06em; text-transform: uppercase; }
.step .t { font-weight: 620; margin-top: 2px; }
.step .d { color: var(--muted); font-size: 0.8rem; margin-top: 2px; }
.step.done .n { color: #1C6B38; }
.step.now { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(61,79,224,0.10); }
.step.now .n { color: var(--accent); }

.next { border-radius: 14px; padding: 18px 20px; background: #EEF0FD; border: 1px solid #D9DDFB; margin-bottom: 0.6rem; }
.next .t { font-weight: 640; font-size: 1.05rem; }
.next .d { color: #3F4166; font-size: 0.9rem; margin-top: 2px; }

.vcard .name { font-weight: 630; font-size: 0.98rem; }
.vcard .meta { color: var(--muted); font-size: 0.8rem; margin: 1px 0 8px 0; }
.vcard .big { font-size: 1.25rem; font-weight: 640; letter-spacing: -0.02em; }
.kv { display:grid; grid-template-columns: 140px 1fr; gap: 6px 12px; font-size: 0.88rem; }
.kv .k { color: var(--muted); }
.quote { border-left: 3px solid var(--line); padding: 2px 0 2px 12px; color: #3A3934; font-size: 0.92rem; margin: 6px 0; }
.how { display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.how div.c { padding: 2px 4px; }
.how .h { font-weight: 620; margin-bottom: 4px; }
.flag { font-size: 0.86rem; padding: 7px 0; border-bottom: 1px solid var(--line); }
.flag:last-child { border-bottom: none; }
.who { display:flex; gap:10px; align-items:center; padding: 6px 2px; }
.who .av { width:32px; height:32px; border-radius:50%; background:#E4E7FB; color:#2F3BB0; font-weight:650; font-size:0.8rem; display:flex; align-items:center; justify-content:center; }
.who .nm { font-weight:600; font-size:0.86rem; line-height:1.2; }
.who .rl { color: var(--muted); font-size:0.75rem; }
.brand { font-weight: 680; font-size: 1.05rem; letter-spacing: -0.01em; }
.brand-sub { color: var(--muted); font-size: 0.78rem; margin-top: -2px; }
.event { border:1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--card); margin-top: 10px; }
.event .id { font-size:0.72rem; color: var(--muted); font-weight:600; letter-spacing:0.04em; }
.event .tt { font-size:0.86rem; font-weight:600; line-height:1.3; margin-top:2px; }
[data-testid="stSpinnerIcon"] { border-color: rgba(61,79,224,0.18) !important; border-top-color: var(--accent) !important; }
[data-testid="stSpinner"] p { color: #3F4166; }
.mailhead { color: var(--muted); font-size: 0.84rem; line-height: 1.6; border-bottom: 1px solid var(--line); padding-bottom: 8px; margin-bottom: 10px; }
.foot { color: var(--muted); font-size: 0.76rem; margin-top: 2.4rem; border-top: 1px solid var(--line); padding-top: 0.8rem; }
@media (max-width: 900px) { .steps, .how { grid-template-columns: 1fr; } }
</style>
"""


def esc(s):
    return html.escape(str(s if s is not None else ""))


def inject():
    st.html(CSS)


def md(s):
    st.markdown(s, unsafe_allow_html=True)


def loading(what, eta):
    """One loader style for every AI wait: what is happening, how long it usually takes, and a running timer."""
    return st.spinner(f"{what} · {eta}", show_time=True)


def mailhead(sender, to):
    md(f"<div class='mailhead'>From: {esc(sender)}<br>To: {esc(to)}</div>")


def pill(status, text=None):
    label, bg, fg, _ = STATUS[status]
    return f"<span class='pill' style='background:{bg};color:{fg}'>{esc(text or label)}</span>"


def tag(text, bg="#F2F2F0", fg="#4A4945"):
    return f"<span class='pill' style='background:{bg};color:{fg}'>{esc(text)}</span>"


QUAL = {"pass": ("Qualified", "#E8F5EC", "#1C6B38"), "fail": ("Not qualified", "#FDECE8", "#B4321B"),
        "unverified": ("Unverified", "#FDF4DC", "#8A5A00")}


def qual_tag(status):
    t, bg, fg = QUAL.get(status, (status, "#F2F2F0", "#4A4945"))
    return tag(t, bg, fg)


def legend(note=None):
    items = "".join(pill(k) for k in STATUS)
    md(f"<div class='legend'>{items}" + (f"<span class='note'>{esc(note)}</span>" if note else "") + "</div>")


def header(eyebrow, title, sub=None):
    md(f"<div class='eyebrow'>{esc(eyebrow)}</div>")
    st.title(title, anchor=False)
    if sub:
        md(f"<div class='sub'>{sub}</div>")


def steps(items):
    """items: list of (state, title, detail) where state in done/now/todo."""
    cells = []
    for i, (state, t, d) in enumerate(items, 1):
        mark = "Done" if state == "done" else ("Now" if state == "now" else f"Step {i}")
        cells.append(f"<div class='step {state}'><div class='n'>{i} · {mark}</div><div class='t'>{esc(t)}</div><div class='d'>{esc(d)}</div></div>")
    md(f"<div class='steps'>{''.join(cells)}</div>")


def footer():
    md("<div class='foot'>Prototype for a product assignment. Every company, person and price is fictional. "
       "Vendor emails are simulated; reading, reasoning and analysis are live model calls.</div>")


def inr(x):
    if x is None:
        return "–"
    return f"₹{x/1e7:.2f} cr" if abs(x) >= 1e7 else f"₹{x/1e5:.1f} L"

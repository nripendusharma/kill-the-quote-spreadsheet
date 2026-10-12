"""Paths and loaders for the seeded RFx and the demo inbox."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
INBOX = DATA / "vendor_responses"
ATTACH = DATA / "attachments"
STATE = ROOT / "app" / "state"
STATE.mkdir(exist_ok=True)
TODAY = "2026-10-12"  # demo "today", used for certificate expiry checks

# Which files make up each vendor's reply in the demo inbox (the "channel" is stubbed email)
DEMO_INBOX = {
    "A": dict(files=["A_HosurCorrutech_Quotation.xlsx"], attachments=["A_ISO9001_certificate.pdf", "A_BCT_test_report.pdf"],
              email="Please find attached our quotation and technical compliance sheet. Regards, Hosur Corrutech."),
    "B": dict(files=["B_PacificFibre_Offer.pdf"], attachments=["B_ISO9001_certificate.pdf", "B_test_report.pdf"],
              email="Dear Ms Rao, please find our commercial offer attached. Best, Rohan Mehta."),
    "C": dict(files=["C_KaveriKraft_Quotation.docx"], attachments=[], email="Madam, our quotation is attached. Kindly consider."),
    "D": dict(files=["D_SriLakshmi_email.txt", "D_SriLakshmi_RateCard_photo.jpg"],
              attachments=["D_ISO9001_certificate.pdf", "D_BCT_test_report.pdf"], email=None),
    "E": dict(files=["E_DeccanCorrugators_email.txt"], attachments=[], email=None),
}


def load_rfx():
    return json.loads((DATA / "rfx.json").read_text(encoding="utf-8"))


def load_last_year():
    with open(DATA / "last_year_contract.csv", encoding="utf-8") as f:
        return {r["line_id"]: r for r in csv.DictReader(f)}


def load_answer_key():
    return json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))

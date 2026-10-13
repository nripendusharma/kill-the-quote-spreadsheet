# Kill the Quote Spreadsheet: what I decided, and what I left out

**One sentence:** a buyer drafts an RFx with a co-pilot, five vendors reply however they like, and the system reads every reply into one comparison where every number carries its source, its conversion and its confidence, so a buyer can defend a Rs 4 crore award to their VP.

## The decisions that mattered

1. **The model reads; code calculates; a person signs off on doubt.** Claude extracts prices exactly as written, with a verbatim quote, a location and a confidence score. Every conversion (per 100 pcs, per kg via board weight, USD, GST-inclusive, freight) and every total runs in plain code. The analyst never does arithmetic: it calls SQL and an optimiser. *Why:* a misread digit is recoverable if it is visible; a hallucinated sum inside a fluent answer is not.
2. **Six cell states, always visible.** Verified, Converted, Buyer-confirmed, Inferred, Needs review, Not quoted. *Why:* the buyer's real question is not "what is the price" but "can I act on this price".
3. **Untrusted prices are held out of the award by default.** A missing line is never zero and never cheapest. "Rest same as last year" is filled from last year's contract but marked Inferred until confirmed. A unit the vendor never stated is shown with its most plausible reading, held for review. *Why:* the cost of a wrong award is far higher than the cost of one more question to a vendor.
4. **Trust the documents, not the vendor's say-so.** Qualification is checked against what was attached: Pacific Fibre says "ISO certified", the attached certificate expired in March. *Why:* the VP's question ("only vendors who cleared the questionnaire") is only as good as that check.
5. **Corrugated packaging as the category.** It has the hardest honest unit problem: "Rs 42/kg for the 5-ply" can only be compared once you compute each box's board weight from its dimensions and GSM. *Why:* it forces the system to know the domain, not just parse text.
6. **Measured, not claimed.** I fabricated the dataset, so I know the right answer for every cell. The scorecard shows how many cells the reader got right, how many errors the review gate caught, and how many slipped through as trusted. *Why:* "would a buyer act on this?" deserves a number.
7. **Streamlit over a polished front end.** 48 hours went into the AI loops and the edge cases, which is what the brief said it cares about.

## What I deliberately left out

Real email in and out (stubbed; the inbox is seeded), vendor portal and logins, multi-round negotiation, versioning of revised quotes, roles and approvals, ERP/PO push, more than one category per RFx, hedging FX exposure, and freight modelled per lane (it is a single editable % assumption, clearly labelled).

## The better problem

The brief prices the pain at three days of retyping. But "nine days" is mostly the back-and-forth that follows: chasing the vendor who skipped three lines, asking what "same as last year" means, asking how freight is charged. Once the system knows exactly what is ambiguous, it can **draft every clarification to every vendor on day one**, in one email per vendor. The bigger win is not faster reading; it is **one round of clarification instead of four**. The review queue already does a small version of this.

## What I would measure in production

Share of cells auto-trusted; reading accuracy by format (photo vs PDF vs prose); buyer override rate (a rising rate means the reader is drifting); clarification rounds per RFx; days from last reply to award.

*Built with Claude Code. Live model: Claude Sonnet 5.5 (the stored demo readings and both accuracy runs were made with Claude Opus 5.5). All companies, people and prices are fictional.*

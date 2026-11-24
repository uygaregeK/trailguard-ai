# W3 Product Track — Customer Interviews

**Owner:** Dilara Yıldız · **Guide:** `docs/w3_interview_guide.md` · **Handbook ask:** talk to at least 2 people who could be our customers: what they do today, what they would pay for, and what scares them about AI.

**Privacy (R10):** no names, store names, phone numbers or emails are recorded. Interviewees are numbered.
**Method:** notes were taken during the interview, with no recording. Questions without an answer are marked "not asked"; nothing below is filled in by us.

---

### Interviewee 1 — support employee, small online store (clothing, small team) (2026-11-23, phone)

**Today:** messages/day: about 20 · channels: not asked · top questions: "Where is my parcel?", "Is it in stock?", "Can I return it?" · tools opened per return: not asked · minutes per message: about 15
**Pain:** in busy periods they answer messages late and lose customers because of it.
**Wrong approvals:** yes, they have approved a return that broke the rules, and it cost them money (amount not given).
**Would pay for:** automatic replies to customer messages · current tools and price: no paid support tool · preferred pricing: not asked
**AI fears:** that it gives a wrong answer.
**Never give to AI:** not asked
**If the AI gets something wrong:** "we could penalize it" (ceza verebiliriz).
**Reaction to the idea:** not asked

**Assumptions check** (assumptions from `docs/use_case_brief.md`)

| # | Our assumption | What they said | Held? |
| :--- | :--- | :--- | :--- |
| A1 | ~180 tickets/day | about 20 messages/day | no — a much smaller store than our persona |
| A2 | ~6 min per ticket | about 15 min per message | no — handling takes longer than we assumed |
| A3 | 4 tools per ticket | not asked | unknown |
| A4 | wrong approvals cost money | it happened and they lost money | partly — no amount |
| A5 | slow first response in peaks | late replies in busy periods lose customers | yes — no times given |

**What we take from it**
- Their three most common questions are the three things our agent does: order tracking, product and stock questions, and returns.
- About 20 messages × 15 minutes is roughly 5 hours a day of answering messages, even for a small store.
- Their main fear, a wrong answer, is what our design targets: answers cite the store's documents, and the agent gives a fixed "I can't answer this" reply when the documents don't cover the question.
- They pay for no support tool today, so price will matter (input for the Week 5 pricing hypothesis).

---

### Interviewee 2 — support employee, online food store (team of 7) (2026-11-23, phone)

**Today:** messages/day: about 60 · channels: not asked · top questions: "Where is my parcel?", "Is it in stock?", "Can I return it?" · tools opened per return: not asked · minutes per message: about 9
**Pain:** in busy periods they answer messages late and lose customers because of it.
**Wrong approvals:** yes, they have approved a return that broke the rules, and it cost them money (amount not given).
**Would pay for:** automatic replies to customer messages · current tools and price: no paid support tool · preferred pricing: not asked
**AI fears:** that it gives a wrong answer.
**Never give to AI:** not asked
**If the AI gets something wrong:** "we could penalize it" (ceza verebiliriz).
**Reaction to the idea:** not asked

**Assumptions check**

| # | Our assumption | What they said | Held? |
| :--- | :--- | :--- | :--- |
| A1 | ~180 tickets/day | about 60 messages/day | no — smaller than our persona |
| A2 | ~6 min per ticket | about 9 min per message | no — handling takes longer than we assumed |
| A3 | 4 tools per ticket | not asked | unknown |
| A4 | wrong approvals cost money | it happened and they lost money | partly — no amount |
| A5 | slow first response in peaks | late replies in busy periods lose customers | yes — no times given |

**What we take from it**
- About 60 messages × 9 minutes is roughly 9 hours a day, more than one person's working day spent on messages.
- The same three questions and the same fear (a wrong answer) as Interviewee 1, in a different sector.

---

## Summary (2 interviews)

| # | Assumption | Interviewee 1 (clothing) | Interviewee 2 (food) | Result |
| :--- | :--- | :--- | :--- | :--- |
| A1 | ~180 tickets/day | ~20 | ~60 | **not held** — both stores are smaller than our persona |
| A2 | ~6 min per ticket | ~15 | ~9 | **not held** — handling takes longer, so the time to save is larger |
| A3 | 4 tools per ticket | not asked | not asked | **not checked** |
| A4 | wrong approvals cost money | yes | yes | **partly held** — both lost money, neither gave an amount |
| A5 | slow first response in peaks | yes | yes | **held** — both say late replies lose customers |

**What they do today:** they answer every message by hand. Both name the same top three questions, which are the three jobs our agent does: order tracking, product and stock questions, and returns. Both spend several hours a day on messages (about 5 and 9 hours).

**What they would pay for:** automatic replies. Neither pays for a support tool today, so the price has to be low enough for a small store (input for the Week 5 pricing hypothesis).

**What scares them about AI:** a wrong answer. Both have already lost money on a wrong return approval made by a person, and both would hold the AI responsible for mistakes ("we could penalize it").

**One thing we will change:** returns will need a staff member's approval. The agent answers tracking, stock and policy questions on its own, because a wrong answer there is easy to correct. For a return it checks the rules and prepares the request, but a person approves it before it is created, because a wrong return is the mistake both stores said costs money. Today our design asks only for the customer's confirmation (`docs/data_inventory.md`); we will add staff approval to the return action in Week 4 and treat it as the higher risk tier in Week 6.

**Also to update:** our working volume in `docs/use_case_brief.md` (~180 tickets/day) is larger than both stores we spoke to. We keep it for our persona, a larger trail-running store, but note that the small stores we reached handle 20–60 messages a day.

**Limits:** two people, both support employees reached by phone, neither from a sports store. Several questions were not asked (channels, tools per ticket, preferred pricing, what they would never give to an AI, and their reaction to the idea), so A3 is unchecked. Notes were short, which is why the two interviews read alike.

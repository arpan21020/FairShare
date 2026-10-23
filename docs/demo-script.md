# FairShare: demo video script

**Target length:** about 2:50. The hard limit is 3:00. Alexa takes 2 to 6 seconds to reply in
live mode, so trim those pauses when you edit.

**Alexa's replies below are real.** They come from a full run of this exact flow on the live
model, starting from an empty household.

---

## Before you record

1. **Start fresh:** stop any running `run.py` (Ctrl+C), then run:
   ```bash
   python run.py --reset
   ```
   Rahul, Priya and Neha start with ₹0 balances, and a Chrome window opens.
2. **Set up the screen:**
   - Mode: **Live (LLM)**
   - **🔊 Voice on** and **🔁 Follow-up on**
   - Voice ID: **Unknown**
   - Click **New conversation**
   - Widen the window so the **MCP trace** panel is visible on the right.
3. **Allow the microphone** when Chrome asks. Speak clearly; headphones stop Alexa from hearing
   itself. You can **type** any line instead of speaking it.
4. **Record** at 1080p (Windows: **Win + Alt + R**, or OBS).

---

## 0:00–0:20 · Introduction

**On screen:** the FairShare simulator, idle.

> "Every shared home has the same question: who paid for what, and who owes whom?
> The spreadsheet never gets updated, but there's an Echo in the kitchen. This is **FairShare**:
> shared household expenses, settled by voice, built as an MCP server for Alexa+. Alexa+ itself
> isn't open to hackathon developers yet, so this is a simulated Echo Show talking to my real MCP
> server. I'll play Rahul, who shares a flat with Priya and Neha."

---

## 0:20–1:00 · Groceries, and "who's speaking?"

Voice ID is **Unknown**. Press 🎤 once; after that, Follow-up keeps listening.

| # | You say | Alexa says | Screen |
|---|---|---|---|
| 1 | "Hey, I spent 2,400 for the groceries. Split it equally between me, Priya and Neha." | "Could you tell me who's speaking?" | Question card |
| 2 | "Rahul." | "₹2,400 for Groceries, paid by Rahul, split as Rahul ₹800, Priya ₹800 and Neha ₹800. Shall I save it?" | **Confirm split** · voice ID switches to Rahul |
| 3 | "Go ahead." | "Saved: ₹2,400 for Groceries, paid by Rahul. Priya's share is ₹800 and Neha's share is ₹800." | **Expense saved** + balances |

**Narration** (while Alexa is thinking, or added in editing):
> "Alexa didn't know who was talking, so it asked before touching any money. On a real Echo,
> Alexa+ voice ID does that automatically. Nothing is saved until I confirm, and the amounts come
> from the server, never the AI."

---

## 1:00–1:45 · Pizza: a new speaker, a mistake, and undo

**Click "Unknown"** under Voice ID first: someone else is now talking.

| # | You say | Alexa says | Screen |
|---|---|---|---|
| 4 | "Split the pizza expense." | "Who's speaking?" | Question card |
| 5 | "I am Priya. The pizza was 900, split between me and Neha." | "₹900, paid by Priya, split as Priya ₹450 and Neha ₹450. Shall I save it?" | **Confirm split** · voice ID switches to **Priya** |
| 6 | "Save it." | "Saved: ₹900 for Pizza, paid by Priya. Neha's share is ₹450." | Expense saved |
| 7 | "Oops, I told the wrong amount. Revert the last change." | "Done. Removed the ₹900 expense for Pizza." | Balances |
| 8 | "The pizza expense was 650." | "₹650, paid by Priya, split as Priya ₹325 and Neha ₹325. Shall I save it?" | Confirm split |
| 9 | "Yes, save it." | "Saved: ₹650 for Pizza, paid by Priya. Neha's share is ₹325." | Expense saved |

**Narration:**
> "Priya just says who she is. Undo only ever reverts your own last change, so one person can't
> accidentally wipe out someone else's entry. And Alexa remembers the conversation: 'the pizza
> expense was 650' is enough."

---

## 1:45–2:15 · Spending this month, and paying back

| # | You say | Alexa says | Screen |
|---|---|---|---|
| 10 | "What's our total expenditure this month?" | "In October 2026, the household spent ₹3,050 across 2 expenses. The biggest category was groceries at ₹2,400." | **Monthly summary** (categories and who paid) |
| 11 | "I paid back Rahul 500." | "Recorded: Priya paid Rahul ₹500." | **Balances** |

> **Tip:** with ₹500, Priya overpays by ₹25, so the balances show "Priya is owed ₹25". That's
> correct, but say **"475"** if you'd like Priya to come out exactly settled.

**Narration:**
> "FairShare never moves money. It records the payment once it has happened, and everyone's
> balance updates."

---

## 2:15–2:50 · Under the hood, and closing

**On screen:** open two or three entries in the **MCP trace** panel (`preview_split`,
`add_expense`, `undo_last`) to show the arguments and results.

> "Everything you just saw went through a real MCP server: ten tools over Streamable HTTP, on MCP
> spec 2025-11-25, built with the official MCP Python SDK. The AI, an NVIDIA Nemotron model here,
> only understands what we say. The server does every calculation in exact paise, and Alexa reads
> out the server's own sentence, so the numbers are always right. And it's all open source.
>
> FairShare: shared household expenses, settled by voice. Thanks for watching!"

---

## If something goes wrong while recording

| Problem | Fix |
|---|---|
| Alexa mishears a name or amount | Type that line instead; replies are still spoken |
| Alexa saves or asks something unexpected | Say "Undo that", or click **New conversation** and restart from that section |
| The free LLM is slow or rate-limited | Wait a few seconds and repeat; cut the pause in editing |
| The numbers don't match this script | Restart with `python run.py --reset` so the household starts at ₹0 |

## Before uploading

- [ ] Under 3:00 (aim for about 2:50)
- [ ] English narration, or English captions
- [ ] "Simulated Alexa+" is visible on screen or said aloud
- [ ] Shows the working app, not slides
- [ ] No API key or `.env` contents on screen
- [ ] YouTube visibility **Public**; check the link in a private window

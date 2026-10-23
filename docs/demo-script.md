# FairShare — demo video script (target 2:45, hard limit 3:00)

## Before recording

1. Start from an empty household so the numbers are small and easy to follow:
   ```bash
   python run.py --reset
   ```
   A new Chrome window opens at http://127.0.0.1:8001. Every balance starts at ₹0.
2. In the browser: **Voice on** and **Follow-up on**; select **Unknown** under
   *Voice ID (simulated)*, allow the microphone, and widen the window so the **MCP trace** panel
   is visible on the right. Press the 🎤 once to start; after each reply, just keep talking (the
   screen glows while it listens, and shows the words it hears).
3. Choose the mode:
   - **Live (LLM)** for the AI segments (recommended: it shows real understanding). Expect
     2–6 seconds per reply; trim the waits when editing.
   - **Scripted** as the fallback: every line below is in the script, so clicking the suggestion
     buttons gives exactly the same results with no waiting.
4. Record at 1080p (Windows: Xbox Game Bar, Win+Alt+R, or OBS). Upload to YouTube as **Public**,
   English, under 3 minutes, and check the link in a private window.

Expected numbers below assume an empty household (`--reset`, no `--seed`).

---

## 0:00–0:15 · The problem

**On screen:** the FairShare simulator, idle.

**Narration:** "Every shared home has the same question: who paid for what, and who owes whom?
Nobody updates the spreadsheet. But you're standing next to an Echo Show. FairShare lets the
household settle it by voice."

## 0:15–0:55 · A messy split, and knowing who's speaking (Live)

Voice ID is **Unknown**. Say or type:

| Say | Alexa replies (approximately in live mode) | Screen |
|---|---|---|
| "I paid ₹2,400 for groceries. Split it with Priya and Neha, but Neha was away half the week." | Asks who's speaking | Question card |
| "Rahul." | "₹2,400 …, paid by Rahul, split as Rahul ₹960, Priya ₹960 and Neha ₹480. Shall I save it?" | **Confirm split** card |
| "Yes, save it." | "Saved: ₹2,400 for Groceries, paid by Rahul. Priya's share is ₹960 and Neha's share is ₹480." | **Expense saved** card with balances |

**Narration (over the waits):** "On a real Echo, Alexa+ voice ID knows who's talking. Here it's
simulated, so Alexa asks before changing anything. The AI understands 'away half the week' as
half a share, and FairShare's server does the maths in exact paise. Nothing is saved until Rahul
confirms."

*Scripted fallback:* select **Rahul**, then click the first two suggestions.

## 0:55–1:25 · Ask instead of guessing, and undo

| Say | Alexa replies | Screen |
|---|---|---|
| "This is Priya. Split the pizza." | "How much was the pizza, and who shared it?" | Question card; voice ID switches to **Priya** |
| "It was ₹900, just me and Neha." | "Saved: ₹900 for Pizza, paid by Priya. Neha's share is ₹450." | Expense saved |
| "Oops, that was the wrong amount. Undo that." | "Done. Removed the ₹900 expense for Pizza." | Balances |

**Narration:** "Priya just says who she is. When something's missing, Alexa asks rather than
guesses, and undo only ever reverts your own last change."

## 1:25–1:50 · Who owes what, and paying back

| Say | Alexa replies | Screen |
|---|---|---|
| "Who owes what?" | "Rahul is owed ₹1,440, Priya owes ₹960 and Neha owes ₹480." | **Balances** card |
| "I paid Rahul back ₹500." | "Recorded: Priya paid Rahul ₹500." | Balances: Rahul ₹940, Priya ₹460, Neha ₹480 |

**Narration:** "Balances update for everyone, and words and arrows show who owes, not just colours."

## 1:50–2:10 · Settle up

Switch voice ID to **Neha** (or say "This is Neha. …").

| Say | Alexa replies | Screen |
|---|---|---|
| "Settle up. What's the fewest payments?" | "To settle up: Neha pays Rahul ₹480 and Priya pays Rahul ₹460. That's 2 payments." | **Settle up** card with arrows |
| "How much did we spend this month?" | "In October 2026, the household spent ₹2,400 across 1 expense. The biggest category was groceries at ₹2,400." | **Monthly summary** |

**Narration:** "Settle up turns the month into a couple of payments. FairShare never moves money;
it just tells you who pays whom."

## 2:10–2:45 · Under the hood

**On screen:** open a few entries in the **MCP trace** panel (`preview_split`, `add_expense`), then
show the README's tool list or the terminal.

**Narration:** "Everything you saw is a real MCP server: ten tools over Streamable HTTP, MCP spec
2025-11-25, built with the official MCP Python SDK. The LLM, an NVIDIA Nemotron model here,
only understands the request. The server does every calculation, and Alexa speaks the server's
own sentence, so the numbers are always exact. It's labelled a simulated Alexa+ device because
Alexa+ integration isn't open to hackathon participants, but this server is exactly what Alexa+
would call. FairShare: shared household expenses, settled by voice."

---

## Checklist before uploading

- [ ] Under 3:00 (aim for 2:45)
- [ ] English narration or captions
- [ ] "Simulated Alexa+" is visible or said
- [ ] Shows the working app, not slides
- [ ] No API key or `.env` contents on screen
- [ ] YouTube visibility **Public**; link works in a private window

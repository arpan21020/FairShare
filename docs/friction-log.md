# Friction Log — FairShare (Alexa+ track)

What slowed us down while building FairShare, a self-hosted MCP server for Alexa+, and what
would help the next developer. Each entry: what happened, the impact, our workaround, and a
suggestion.

## Top suggestions for Alexa+

1. **Tell MCP servers who is speaking.** Alexa+ voice ID knows which household member is
   talking, but there is no documented way for an MCP server to receive that identity. Money,
   chores and reminders all depend on it. (Entry 3.)
2. **Publish how Alexa+ renders MCP tool results on screen devices.** We had to invent our own
   `display` card hints for the Echo Show. (Entry 4.)
3. **Let a tool's reply be spoken verbatim.** An LLM paraphrase of exact figures attached the
   right amounts to the wrong people. (Entry 5.)
4. **Give participants a test harness.** The Alexa+ toolkit and web simulator are partner-only,
   so we couldn't test tool descriptions against the real assistant. (Entry 1.)
5. **State the MCP spec version Alexa+ negotiates**, and show how to test against it. (Entry 7.)

---

## Alexa+ and the hackathon

### 1. Alexa+ integration not available to participants
- **What:** The Alexa+ Add-on toolkit and web simulator are in preview with select partners only,
  so entries cannot be tested on Alexa+ itself.
- **Impact:** We built our own Echo Show-style simulator and an LLM orchestrator to stand in for
  Alexa+. We can't confirm how the real assistant would choose between our tools, phrase
  confirmations, or handle our errors.
- **Suggestion:** A public, rate-limited Alexa+ MCP test harness, even text-only, that connects to
  a developer's MCP URL and shows which tools Alexa+ would call.

### 2. Devpost rules and resources pages not machine-readable
- **What:** Fetching the rules and resources pages from tooling returned HTTP 403, so
  requirements were pieced together from the community announcement and search summaries.
- **Impact:** Uncertainty about exact judging weights and video hosting rules.
- **Workaround:** Checked the pages manually in a browser.
- **Suggestion:** Also publish the rules as a plain page or a file in the starter repo.

### 3. No way for an MCP server to know which household member is speaking
- **What:** A shared-expense ledger must know who said "I paid ₹500". Alexa+ voice ID solves this
  for Amazon's own features, but nothing documented passes the recognised speaker to an MCP tool.
- **Impact:** Every FairShare tool takes an explicit `actor` argument, which the assistant has to
  fill in. We simulated voice ID with a selector, plus detection of "This is Priya…", and told the
  LLM to ask "Who's speaking?" before any write when the speaker is unknown.
- **Suggestion:** Pass the recognised voice profile (or an opaque, stable household-member id
  plus display name) in the request `_meta` to MCP servers the household has enabled, with user
  consent. Many household skills (money, chores, kids' rewards) need this.

### 4. No guidance on rendering MCP results on screen devices
- **What:** Alexa is voice-first but not voice-only, and the judges expect a multimodal
  experience. We found no documentation on how Alexa+ displays an MCP tool's `structuredContent`
  on an Echo Show, or whether servers can suggest a layout.
- **Impact:** We designed our own convention: each result has `speech`, `data` and a `display`
  hint (`confirm_split`, `balances`, `settle_up`, …), and our simulator renders the cards.
- **Suggestion:** Publish the rendering contract (for example, how `outputSchema`,
  `structuredContent` and any APL-style templates map to the screen), with a few example card
  types.

### 5. LLM paraphrases can misstate exact figures
- **What:** During testing the tool returned "Rahul ₹960, Priya ₹960 and Neha ₹480", and the LLM
  replied "₹960 each for Priya and Neha, and ₹480 for you": the right amounts, attached to the
  wrong people.
- **Impact:** For money, a confident wrong sentence is worse than an error.
- **Workaround:** After a successful tool call, our host speaks the tool's own `speech` field,
  generated from exact ledger numbers; the LLM's own words are used only when no tool ran (for
  example, clarifying questions). Write tools are previewed and confirmed before saving.
- **Suggestion:** A way for a tool to mark its reply as "speak verbatim" (for example, a result
  annotation), and documented Alexa+ behaviour for confirming financial or destructive actions.

---

## MCP SDK

### 6. MCP Python SDK v2 API differs from most examples online
- **What:** The current `mcp` package (2.3.0) uses `MCPServer` and `Client`, while most blog posts
  and samples still show v1's `FastMCP` and `streamablehttp_client`/`ClientSession`. The README
  doesn't state which MCP protocol versions are supported; we read `mcp_types/version.py` to
  confirm 2025-11-25 (handshake) and 2026-07-28 support.
- **Impact:** Extra time verifying the setup and spec compliance.
- **Suggestion:** State the supported protocol revisions in the README and in the hackathon
  starter template.

### 7. Two protocol "eras" in the SDK; the default client skips 2025-11-25
- **What:** `Client(url)` defaults to `mode="auto"`, which negotiates 2026-07-28. To prove the
  server meets the hackathon's 2025-11-25 requirement we had to know to pass `mode="legacy"`.
- **Impact:** It's easy to ship a server only ever tested on the newest protocol.
- **Workaround:** Our protocol tests run over Streamable HTTP in both modes and assert the
  negotiated version.
- **Suggestion:** Document which spec version Alexa+ negotiates, and include a
  "test against 2025-11-25" snippet in the starter template.

### 8. Tool error text is prefixed
- **What:** `ToolError("I don't know anyone called Raj…")` reaches the client as
  `Error executing tool add_expense: I don't know anyone called Raj…`.
- **Impact:** Our errors are written to be spoken, but carry a technical prefix the host must strip.
- **Workaround:** The orchestrator strips the prefix before speaking.
- **Suggestion:** An option to return the message verbatim.

---

## LLM and tooling

### 9. Choosing a free LLM that can call tools reliably took trial and error
- **What:** We used NVIDIA's free OpenAI-compatible endpoint. The model list mixes chat models
  with embedding and rerank models, some listed models returned 404 for our account, and nothing
  says which models support tool calling. Results varied widely on our demo turn:
  - `nemotron-3-ultra`: correct, but 15–23 s per turn;
  - `nemotron-3.5-lightning` without thinking: 1–4 s, but ignored "Neha was away half the week"
    and invented an amount;
  - `nemotron-3.5-lightning` with thinking: correct in 3/3 runs, about 2–6 s per turn;
  - `gpt-oss-20b`: wrong split and 80–100 s per turn.
- **Impact:** About an hour of model evaluation during the hackathon.
- **Workaround:** A small script that replays the demo turns against a temporary server and
  prints each tool call, plus clearer tool descriptions ("away part of the time → weights; never
  work out amounts yourself").
- **Suggestion:** For an Alexa+ developer kit: a recommended tool-calling eval (a handful of
  utterances with expected tool calls) that developers can run against their own tool
  descriptions.

### 10. Small breaking changes in the Python ecosystem
- **What:** The `openai` Python SDK v3 moved its HTTP layer from `httpx` to `httpx2`, which broke a
  test that constructed a connection error.
- **Impact:** Minor; a few minutes.
- **Suggestion:** None needed for Amazon; noted for completeness.

### 11. Local development on Windows
- **What:** Port 8000 (the usual MCP example port) was already used by another program, and SQLite
  database files can't be deleted on Windows while the server holds them open.
- **Impact:** A confusing "Not Found" from the wrong server, and a failed reset.
- **Workaround:** FairShare defaults to port 8010, checks that ports are free before starting
  (`run.py`), and gives a clear message if the database is in use.
- **Suggestion:** Starter templates could pick a less common default port and show how to change it.

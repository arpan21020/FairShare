# HouseLedger

Shared household expenses, settled by voice — a self-hosted MCP server for Alexa+.

> Work in progress for the Build, Ship, Shape: Amazon Developer Hackathon 2026 (Alexa+ track).
> The full README (architecture, demo, simulator) is coming.

## Run the MCP server

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv run python -m houseledger.mcp_server --seed
```

- MCP endpoint (Streamable HTTP): `http://127.0.0.1:8010/mcp`
- Health check: `http://127.0.0.1:8010/health`
- Protocol: MCP spec **2025-11-25** (initialize handshake) and 2026-07-28, via the official MCP Python SDK.
- `--seed` adds a demo household (Aarav, Priya, Sam) with **seeded, fictional** expenses.

## Tools

| Tool | What it does |
|---|---|
| `list_household_members` | Household members' names |
| `preview_split` | Work out a split without saving it, to read back for confirmation |
| `add_expense` | Save a shared expense (equal, weighted, percentage, exact, or with items for specific people) |
| `edit_expense` | Change an expense |
| `undo_last` | Undo the speaker's own last action |
| `record_payment` | Record that one member paid another back |
| `get_balances` | Who owes what |
| `settle_up_plan` | Suggested payments to settle everyone up (never moves money) |
| `list_expenses` | Recent expenses and payments |
| `monthly_summary` | Spending for a month by category and member |

Every tool returns a short spoken reply as text, plus structured content `{speech, data, display}`.
All money is calculated in integer paise by the server; the assistant never does the arithmetic.

## Run the simulated Alexa+ device

Alexa+ integration isn't available to hackathon participants, so an Echo Show-style simulator
stands in for it. It is a real MCP host: it calls the server above over Streamable HTTP.

```bash
# terminal 1 — MCP server (above)
cd backend && uv run python -m houseledger.mcp_server --seed

# terminal 2 — orchestrator (the "Alexa" brain), http://127.0.0.1:8001
cd backend && uv run python -m orchestrator.app

# terminal 3 — screen, http://localhost:5173
cd simulator && npm install && npm run dev
```

- **Live mode:** an LLM (any OpenAI-compatible endpoint; NVIDIA by default) plays Alexa and decides
  which tools to call. Put `NVIDIA_API_KEY=...` in `.env` (see `.env.example`).
- **Scripted mode:** no key needed — replays the demo conversation through the same MCP tools.
- Alternatively run `npm run build` in `simulator/`; the orchestrator then serves the screen itself at
  http://127.0.0.1:8001.

## Tests

```bash
cd backend
uv run pytest -q
```

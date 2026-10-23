# HouseLedger

Shared household expenses, settled by voice — a self-hosted MCP server for Alexa+.

> Work in progress for the Build, Ship, Shape: Amazon Developer Hackathon 2026 (Alexa+ track).
> The full README (architecture, demo, simulator) is coming.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12+ and the backend packages automatically)
- [Node.js](https://nodejs.org/) 20.19+ or 22.12+ with npm (for the simulator screen)
- Optional, for live mode: a free [NVIDIA API key](https://build.nvidia.com/) or any OpenAI-compatible LLM endpoint

## Quick start (from a fresh clone)

```bash
git clone https://github.com/arpan21020/FairShare.git
cd FairShare
python run.py          # macOS/Linux may need: python3 run.py
```

`run.py` works on Windows, macOS and Linux. It installs what's needed, builds the screen if it
changed, starts the MCP server and then the orchestrator, and opens **http://127.0.0.1:8001**.
Press **Ctrl+C** to stop everything.

| Option | Effect |
|---|---|
| `--seed` | add a few weeks of seeded, fictional sample expenses |
| `--reset` | wipe the ledger first (members only, zero balances); combine with `--seed` for fresh samples |
| `--no-browser` | don't open a browser window |
| `--build` | force a rebuild of the screen |
| `--mcp-port`, `--port` | change the ports (defaults 8010 and 8001) |

**Live (LLM) mode** needs a key: copy `.env.example` to `.env` and set `NVIDIA_API_KEY` (or any
OpenAI-compatible `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`). Without a key, use **Scripted** mode.

### Manual start (what run.py does)

```bash
# 1. Optional: enable live (LLM) mode — copy the example and add your key
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env

# 2. Start the MCP server (leave running)  ->  http://127.0.0.1:8010/mcp
#    Household members are predefined (Aarav, Priya, Sam), as Alexa+ household profiles would be.
#    Add --seed for a few weeks of seeded, fictional sample expenses.
cd backend
uv run python -m houseledger.mcp_server

# 3. In a second terminal: build the screen, then start the orchestrator  ->  http://127.0.0.1:8001
cd simulator && npm install && npm run build && cd ..
cd backend && uv run python -m orchestrator.app
```

Open **http://127.0.0.1:8001**. Without an API key, use **Scripted** mode.

To start over: stop the MCP server and run `uv run python -m houseledger.seed --reset --empty`
(members only) or `uv run python -m houseledger.seed --reset` (with sample expenses).

## Run the MCP server

```bash
cd backend
uv run python -m houseledger.mcp_server --seed
```

- MCP endpoint (Streamable HTTP): `http://127.0.0.1:8010/mcp`
- Health check: `http://127.0.0.1:8010/health`
- Protocol: MCP spec **2025-11-25** (initialize handshake) and 2026-07-28, via the official MCP Python SDK.
- Household members are predefined (Aarav, Priya, Sam). On a real Echo they would come from the
  Alexa+ household profiles; HouseLedger doesn't manage them.
- `--seed` also adds a few weeks of **seeded, fictional** sample expenses.

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

## License

[MIT](LICENSE)

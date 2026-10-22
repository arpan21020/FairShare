# Friction Log

Problems we ran into while building HouseLedger, for the hackathon's product-feedback
submission. Each entry: what happened, impact, workaround, suggestion.

## 2026-10-22 — Devpost rules and resources pages not machine-readable
- **What:** Fetching the Devpost rules/resources pages from tooling returned HTTP 403, so
  requirements had to be pieced together from the community announcement and search summaries.
- **Impact:** Uncertainty about exact judging weights and video hosting rules.
- **Workaround:** Checked the pages manually in a browser.
- **Suggestion:** Publish the rules as a plain page or PDF in the starter repo too.

## 2026-10-22 — MCP Python SDK v2 API differs from most examples online
- **What:** The current `mcp` package (2.3.0) uses `MCPServer` and `Client`, while most blog
  posts and samples still show v1's `FastMCP` and `streamablehttp_client`/`ClientSession`.
  The README does not state which MCP protocol versions are supported; we had to read
  `mcp_types/version.py` to confirm 2025-11-25 (handshake) and 2026-07-28 (modern) support.
- **Impact:** Extra time verifying the setup and spec compliance.
- **Suggestion:** State supported protocol revisions in the README and in the hackathon
  starter template.

## 2026-10-22 — Alexa+ integration not available to participants
- **What:** The Alexa+ Add-on toolkit and web simulator are in preview with select partners
  only, so entries cannot be tested on Alexa+ itself.
- **Impact:** We built our own Echo Show-style simulator to show the experience.
- **Suggestion:** A public, limited Alexa+ MCP test harness would let entrants validate
  tool descriptions and response shapes against the real assistant.

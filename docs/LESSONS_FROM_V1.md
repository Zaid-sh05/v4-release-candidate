# Lessons from V1/V2 carried into Qanoni V3

V3 preserves the clean-rebuild lessons from V2 rather than reintroducing the old patch stack.

## Runtime and dependencies
- One server process and one port. No separate npm/Vite frontend is required.
- `reload=False` in the normal Windows start path, so the virtual environment is never watched by Uvicorn.
- MCP is written for the current v2 SDK API (`MCPServer`), not mixed v1/v2 imports.
- Port conflicts are detected before Uvicorn starts and reported clearly.
- `.venv` is not shipped in the ZIP.

## Conversation and NLP
- Small talk is handled before legal retrieval.
- A greeting that also contains a legal question remains a legal query.
- The router supports multiple domains for compound cases, e.g. cybercrime + criminal, or criminal + personal status.
- The vocabulary explicitly covers common Arabic/Jordanian phrasing such as الزنا، ابتزاز، فصلني، إشارة حمراء.
- Internal implementation details are not shown to ordinary users.
- The assistant's system instructions explicitly prohibit emojis and invented legal citations.

## Corpus and evidence
- The old database was migrated into a new schema and deduplicated.
- URL-encoded and UUID filenames are cleaned before they reach the UI.
- Canonical official-law documents receive a retrieval boost.
- Generic index/list pages receive a ranking penalty.
- Coverage distinguishes canonical text, partial coverage, and reference-only laws.
- The central Legislation and Opinion Bureau is registered as a reference source without pretending the generic crawler can fully ingest its dynamic site.

## UI
- The interface was rebuilt without the previous CSS/JS cleanup patches.
- There is exactly one central chat scroll container.
- The composer is part of the chat flex layout instead of being globally fixed.
- Suggested questions wrap naturally; there is no horizontal suggestions scrollbar.
- Evidence has its own independent rail and clean source titles.
- No raw MCP paths, retrieval modes, or confidence values are exposed in the normal chat interface.

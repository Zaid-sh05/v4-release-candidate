# V3.6 Final Cloud Integration

V3.6 completes the pilot architecture by connecting the existing grounded legal engine to two optional server-side services:

1. OpenAI Responses API for natural-language synthesis when the direct grounded answer is insufficient.
2. Supabase Postgres + pgvector for hybrid legal retrieval and durable pilot telemetry.

## Data flow

The legal corpus remains bundled locally as a fail-safe. When OpenAI and Supabase are configured, Qanoni embeds the effective user query, calls the Supabase hybrid-search RPC, then feeds only the retrieved official evidence into the answer pipeline. The direct answer engine and evaluator remain in front of the final response.

## Runtime data

Conversation history, feedback, and evaluator outcomes are stored in Supabase when available. This lets public deployments preserve case continuity across requests without relying on a local writable filesystem.

## Fail-closed behavior

If cloud retrieval fails, Qanoni falls back to the bundled SQLite corpus. If the official evidence still does not prove an exact legal value, Qanoni refuses to invent it.

## Deployment security

The service-role key and OpenAI API key are backend environment variables only. Supabase RLS is enabled and no browser-facing policies are created. Admin source synchronization is disabled unless a separate server-side `ADMIN_API_KEY` is configured.

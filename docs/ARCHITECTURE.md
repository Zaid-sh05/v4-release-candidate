# Qanoni Pilot V3 architecture

```text
Browser / PWA
    |
FastAPI API + static UI
    |
Conversation service
    +-- Jordanian Arabic/English NLP router
    +-- Local official-law retrieval (SQLite)
    +-- Direct legal answer engine
    |      +-- penalty extraction
    |      +-- deadline extraction
    |      +-- fee extraction
    |      +-- procedure extraction
    |      +-- judgment/finality evidence
    |      +-- rights extraction
    +-- Optional Supabase hybrid retrieval
    +-- Optional OpenAI grounded synthesis
    |
13 legal-domain MCP servers
    |
Official Jordanian source registry / synchronization engine
```

## Direct-answer principle

Retrieval is not the final user answer. V3 first asks what the user needs: a penalty, duration, fee, procedure, right, judgment status, article, or general explanation. It then extracts the requested value/rule from official evidence where possible.

A source list is evidence **for** the answer; it is not a substitute **for** the answer.

## Fail-closed principle

If exact evidence is missing, the answer engine returns an intent-specific uncertainty message. It does not infer a prison term, fine, appeal period, fee, article number, or judgment finality from model memory.

## Coverage states

- `canonical`: the statute text is locally represented at useful article level.
- `partial`: official text exists, but current consolidated coverage is incomplete.
- `reference_only`: an official authority confirms the law/reference, but the full article text is not locally available.

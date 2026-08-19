# Pilot QA checklist — V3

## Routing

- Greeting -> conversation.
- Fired without notice -> labor / rights.
- Red light penalty -> traffic / penalty.
- Adultery penalty -> criminal / penalty; safe refusal if exact offence text is missing.
- WhatsApp extortion -> cyber + criminal.
- Criminal appeal -> procedure + criminal.
- Sharia appeal deadline -> procedure + personal status / deadline.
- Complaint to Public Prosecutor -> procedure + criminal / complaint.
- Criminal appeal fee -> procedure + criminal / fees.

## Answer contract

- `penalty` -> answer value first as `العقوبة:` when proved.
- `deadline` -> `المدة:` when proved.
- `fees` -> `الرسوم:` when proved.
- `procedure/appeal/complaint` -> `الإجراء:` with usable steps.
- `rights` -> rights/entitlements first.
- `judgment` -> exact finality rule only when supported; otherwise state what facts are missing.
- Never substitute “here are sources” for a value the evidence actually contains.

## Evidence/UI

- Source card is fully clickable.
- No URL-encoded or UUID-like titles in user-facing source cards.
- No raw MCP/RAG/confidence internals in ordinary chat.
- No emojis/emoticons.
- One central chat scroll container; suggestions wrap without horizontal scrollbar.

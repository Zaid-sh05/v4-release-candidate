# Qanoni Pilot V3.5 — Conversation Continuity

V3.5 fixes follow-up case continuity.

## Main fix
When Qanoni asks for missing facts and the user answers in a new message, the new facts are now merged with the recent user-side case context for routing, retrieval, self-evaluation and answer generation.

Example:
1. `فصلني صاحب العمل بدون إنذار، شو حقوقي؟`
2. `عقدي غير محدد المدة، صارلي 4 سنوات، وما أعطوني أي إنذار`

The second turn remains a labor-rights question instead of being misrouted as a generic civil-contract question.

## Labor follow-up behavior
For the verified pilot evidence already in the corpus, Qanoni can now:
- retain the indefinite-contract fact;
- retain service years;
- retain absence of notice;
- calculate the arithmetic implied by the retrieved official-guidance formula while clearly conditioning it on proof of arbitrary dismissal;
- accept a later salary detail and calculate a formula-based estimate;
- ask only for facts that are still missing, especially the employer's stated reason for dismissal.

## Topic reset
A clearly new question such as `ما عقوبة القتل في الأردن؟` is not contaminated by the earlier labor conversation.

## Safety boundary
Conversation memory adapts routing and retrieval. It does not treat user statements as legal authority and does not modify the legal corpus.

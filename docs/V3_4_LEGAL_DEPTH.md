# Qanoni V3.4 — Legal Depth and Self-Checked Retrieval

## Goal

V3.4 addresses a specific pilot weakness: a system can retrieve an official source yet still fail the user by not answering what was asked. Examples include showing sources when the user asked for a punishment, or asking follow-up questions about dismissal without first stating the rights that are already supported by evidence.

## 1. Self-Evaluator

`app/evaluator.py` evaluates each candidate answer against the routed intent.

Examples:

- `penalty` → requires a concrete sanction/penalty/traffic-points result when evidence supports it.
- `deadline` → requires a duration plus trigger/start point, or a specific clarification when there is no universal deadline.
- `fees` → requires a supported amount/scope.
- `procedure` → requires actionable steps.
- `rights` → requires concrete rights; source-only or question-only answers fail.

A failed/weak evaluation does not create an answer. It requests a deeper retrieval pass.

## 2. Adaptive Retrieval

`LegalRepository.adaptive_search()` reruns official-source retrieval with intent-specific query expansions and merges/deduplicates results.

Example for dismissal:

```text
original: فصلني صاحب العمل بدون إنذار شو حقوقي؟
expanded retrieval:
- فصل تعسفي
- بدل الإشعار
- عقد غير محدد المدة
- حقوق العامل
- مدة الخدمة
```

This is retrieval adaptation, not autonomous legal training.

## 3. Labor dismissal depth

V3.4 adds two targeted official evidence anchors:

1. A published Judicial Council principle (تمييز حقوق هيئة عامة 6719/2024) covering arbitrary-dismissal proof issues and the rule that exempting a worker from working during the notice period obliges the employer to pay notice compensation.
2. An official Ministry of Labour explanatory publication stating the Ministry's explanation of the arbitrary-dismissal compensation formula (half a month per year of service, not less than two months) in the context of the published worker-rights case.

Qanoni labels the Ministry item as official guidance and still asks for contract type, service length, termination reason, and notice details before calculating an individual entitlement.

Article 31 is treated as a special economic/technical termination/suspension path, not a generic answer to every dismissal question.

## 4. Feedback loop

The UI adds `مفيد / غير مفيد` buttons. `/api/feedback` stores the rating in SQLite.

Feedback can later be analyzed to improve:

- routing vocabulary,
- search expansion,
- evidence ranking,
- acceptance/regression tests.

It **cannot** directly modify statutes, penalties, deadlines, article text, or source truth.

## 5. Runtime evaluation log

Each legal answer records:

- question,
- intent/domain,
- evaluator score,
- pass/fail,
- evaluator reasons,
- answer mode.

This makes pilot failures measurable instead of relying only on screenshots.

## 6. Safety boundary

Qanoni may adapt how it searches and checks its answer. It may not learn a legal rule from a user's statement, rating, or previous model answer. Legal truth must remain tied to official/verified source material.

## V3.4 acceptance examples

- `فصلني صاحب العمل بدون إنذار شو حقوقي؟` → concrete notice/arbitrary-dismissal rights + needed facts.
- `صاحب العمل قال لا تداوم خلال شهر الإنذار، شو حقي؟` → notice-pay rule.
- `شو عقوبة الزنا؟` → direct supported punishment + legal basis.
- `قطعت إشارة حمراء شو العقوبة؟` → supported points; no invented fine.
- `كم مدة الاستئناف بالحكم الشرعي الغيابي؟` → duration + service trigger.
- `كم رسوم استئناف قضية جزائية؟` → supported fee.


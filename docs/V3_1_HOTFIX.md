# Qanoni Pilot V3.1 Routing Hotfix

## Fixed
- Arabic definite-article/clitic matching in the legal router.
- `ما عقوبة قطع الإشارة الحمراء في الأردن؟` now routes to `traffic`, not `criminal`.
- Traffic retrieval now recognizes `الإشارة الحمراء` / `الاشارة الحمراء` / `إشارة حمراء` consistently.
- Generic intent words such as `عقوبة`, `حبس`, and `سجن` no longer overpower a clearly identified substantive domain.
- Added a regression acceptance test for the exact red-light wording that exposed the bug.

## Verified
The exact query now retrieves `نظام النقاط المرورية لسنة 2024` Article 5 and returns the verified 6 traffic points. It still refuses to invent a monetary fine or imprisonment term if the retrieved official evidence does not clearly establish one.

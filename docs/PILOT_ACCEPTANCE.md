# Pilot acceptance criteria — V3.5

V3.4 is accepted only when the automated checks pass and the following behavior holds:

1. **Penalty questions**
   - return the actual supported punishment/points first.
   - never substitute a source list for the requested value.

2. `شو عقوبة الزنا بالقانون الأردني؟`
   - returns the supported Article 282 punishment and the prosecution-condition caveat.

3. `ما عقوبة القتل بالاردن؟`
   - gives the supported intentional-killing Article 326 path and clearly warns that other homicide classifications differ.

4. `قطعت إشارة حمراء شو العقوبة؟`
   - states the verified traffic points.
   - does not invent a fine or imprisonment value not present in retrieved evidence.

5. `كم مدة الاستئناف بالحكم الشرعي الغيابي؟`
   - returns the supported duration and the issuance/service trigger.

6. `كيف أقدم شكوى عند المدعي العام؟`
   - routes Procedure + Criminal and gives operational steps from official service evidence.

7. `كم رسوم استئناف قضية جزائية؟`
   - returns the supported fee and scope.

8. `تعرضت لابتزاز على واتساب، شو أعمل؟`
   - returns practical official reporting/safety steps, not only the cybercrime penalty.

9. `فصلني صاحب العمل بدون إنذار شو حقوقي؟`
   - states concrete evidence-backed rights including `بدل الإشعار` and the official guidance on `الفصل التعسفي`.
   - asks for contract type, service length, reason, and written notice for case-specific calculation.
   - does not inject Article 31 unless the facts suggest its special economic/technical path.

10. **Self-evaluation**
    - a source-only response to a punishment/rights question is marked weak and triggers adaptive retrieval.

11. **Feedback**
    - helpful/not-helpful ratings are stored for QA and do not change legal facts.

Automated implementation: `tests/test_pilot_acceptance.py` and `tests/test_v34_adaptive.py`.


## V3.5 conversation continuity
- A reply containing requested facts must inherit the previous case context.
- Example: dismissal question -> `عقدي غير محدد المدة، صارلي 4 سنوات...` remains labor/rights.
- A clearly new legal question must not inherit the previous domain.
- User facts may shape routing and arithmetic, but never become legal authority.

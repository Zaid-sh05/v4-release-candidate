from __future__ import annotations

import re
from dataclasses import dataclass

from .models import RouteResult, SourceItem
from .text import normalize_ar

# V3 direct-answer layer
# ----------------------
# This module is intentionally extractive. It may reorganize and shorten an
# official passage, but it must not manufacture a penalty, deadline, fee,
# article number or right that is not present in the retrieved evidence.

AR_PENALTY_MARKERS = (
    'يعاقب', 'الحبس', 'السجن', 'الأشغال', 'الاشغال', 'غرامة', 'الغرامة',
    'العقوبتين', 'العقوبة', 'العقوبات',
)
EN_PENALTY_MARKERS = ('punishable', 'imprisonment', 'prison', 'fine', 'penalty')
AR_APPEAL_MARKERS = (
    'استئناف', 'الاستئناف', 'طعن', 'الطعن', 'تمييز', 'التبليغ', 'تبليغ',
    'وجاهي', 'غيابي', 'تدقيق',
)
EN_APPEAL_MARKERS = ('appeal', 'cassation', 'notice', 'service', 'judgment')

# Use whole-word-ish number tokens. A previous implementation treated the
# substring "ست" inside words such as "المستأنف" as the number six, producing
# false deadline answers. These patterns avoid that class of failure.
AR_NUMBER_WORDS = (
    'واحد', 'واحدة', 'اثنان', 'اثنين', 'اثنتان', 'اثنتين', 'ثلاثة', 'ثلاث',
    'أربعة', 'اربعة', 'أربع', 'اربع', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة',
    'عشرة', 'عشر', 'أحد عشر', 'احد عشر', 'اثنا عشر', 'اثني عشر', 'ثلاثة عشر',
    'أربعة عشر', 'اربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر',
    'تسعة عشر', 'عشرون', 'ثلاثون', 'أربعون', 'اربعون', 'خمسون', 'ستون',
    'سبعون', 'ثمانون', 'تسعون', 'مائة', 'مئة',
)


@dataclass
class GroundedAnswer:
    text: str
    strength: str  # strong | partial | insufficient


def _clean(text: str) -> str:
    text = (text or '').replace('\u00a0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _segments(text: str) -> list[str]:
    """Split legal text into readable clauses while keeping long list lines usable."""
    text = _clean(text)
    if not text:
        return []
    parts = re.split(r'(?<=[\.؟؛:])\s+|\n+', text)
    out=[]
    for p in parts:
        p=p.strip(' -–—\t')
        if len(p) >= 16:
            out.append(p)
    return out


def _dedupe_similar_texts(items: list[str], threshold: float=0.68) -> list[str]:
    """Drop near-duplicate clauses created by overlapping official service summaries."""
    kept=[]; token_sets=[]
    for text in sorted((_clean(x) for x in items if _clean(x)), key=len, reverse=True):
        toks={w for w in normalize_ar(text).split() if len(w)>2}
        duplicate=False
        for prev in token_sets:
            if not toks or not prev:
                continue
            sim=len(toks & prev)/max(1,min(len(toks),len(prev)))
            if sim>=threshold:
                duplicate=True;break
        if not duplicate:
            kept.append(text);token_sets.append(toks)
    return kept


def _query_terms(message: str) -> set[str]:
    n=normalize_ar(message)
    stop={
        'شو','ما','هي','هو','كم','قديش','كيف','بدي','عندي','على','عن','من','في','الى','الي','مع','بدون','هل',
        'عقوبه','عقوبة','غرامه','غرامة','حبس','سجن','مده','مدة','مهله','مهلة','استيناف','استئناف','طعن','حكم','الحكم','متى','متي','قانون','الاردن','الاردني',
        'رسوم','رسم','يصبح','قطعي','قطعيا','نهائي','نهائيا','what','is','the','how','much','many','penalty','fine','deadline','appeal','law','jordan','jordanian','fees','fee',
    }
    return {w.strip('؟?!.,،؛:()[]') for w in n.split() if len(w.strip('؟?!.,،؛:()[]'))>2 and w.strip('؟?!.,،؛:()[]') not in stop}


def _term_overlap(text: str, terms: set[str]) -> int:
    if not terms:
        return 0
    n=normalize_ar(text)
    return sum(1 for t in terms if t and t in n)


def _has_arabic_number(text: str) -> bool:
    ascii_text=text.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    if re.search(r'(?<!\w)\d{1,6}(?!\w)',ascii_text):
        return True
    n=normalize_ar(text)
    for w in AR_NUMBER_WORDS:
        nw=normalize_ar(w)
        if re.search(rf'(?<![\w\u0600-\u06ff]){re.escape(nw)}(?![\w\u0600-\u06ff])',n):
            return True
    return False


def _has_duration_unit(text: str, lang: str) -> bool:
    low=normalize_ar(text) if lang=='ar' else text.lower()
    if lang=='en':
        return any(x in low for x in ('day','days','month','months','year','years','hour','hours'))
    return any(normalize_ar(x) in low for x in ('يوم','يوما','يوماً','أيام','ايام','شهر','أشهر','اشهر','سنة','سنوات','ساعة','ساعات'))


def _deadline_value_phrase(text: str, lang: str) -> str|None:
    """Return an actual duration phrase such as '30 days' or 'ثلاثون يوماً'.

    Law numbers/years (e.g. Law 9 of 1961) must never be mistaken for an appeal
    deadline. The number must be immediately tied to a time unit.
    """
    text=(text or '').translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    if lang=='en':
        m=re.search(r'(?<!\w)(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirty|sixty)\s+(day|days|month|months|year|years|hour|hours)\b', text.lower())
        return m.group(0) if m else None
    n=normalize_ar(text)
    number_words=sorted({normalize_ar(x) for x in AR_NUMBER_WORDS},key=len,reverse=True)
    num=r'(?:\d{1,3}|'+'|'.join(re.escape(x) for x in number_words)+r')'
    unit=r'(?:يوما|يوم|ايام|شهر|اشهر|سنه|سنوات|ساعه|ساعات)'
    m=re.search(rf'(?<![\w\u0600-\u06ff])({num})\s+({unit})(?![\w\u0600-\u06ff])',n)
    return m.group(0) if m else None


def _looks_garbled(text: str) -> bool:
    """Reject visibly broken PDF extraction when clean guidance is available."""
    if not text:
        return True
    weird=0
    for ch in text:
        o=ord(ch)
        # Known corruption ranges seen in imported PDFs, excluding Arabic presentation forms.
        if (0x1000 <= o < 0x2000) or (0x200B <= o <= 0x200F):
            weird += 1
    return weird > max(3, len(text)//55)


def _source_bonus(s: SourceItem) -> float:
    if s.source_kind.startswith('canonical'):
        return 3.0
    if s.source_kind=='official_service':
        return 2.8
    if s.source_kind=='official_guidance':
        return 2.5
    if s.source_kind=='judicial_principle':
        return 3.1
    if s.source_kind in {'canonical_verified','verified_crosscheck'}:
        return 3.4
    if s.source_kind=='official_sync':
        return 1.2
    if s.source_kind=='reference':
        return -1.5
    return 0.0


def _short_rule(seg: str, max_chars: int=650) -> str:
    seg=_clean(seg)
    if len(seg)<=max_chars:
        return seg
    cut=seg[:max_chars]
    p=max(cut.rfind('.'),cut.rfind('؛'),cut.rfind(':'))
    if p>max_chars*0.55:
        cut=cut[:p+1]
    else:
        cut=cut.rsplit(' ',1)[0]+'…'
    return cut


def _legal_basis(source: SourceItem, i: int, lang: str) -> str:
    title=source.title or ''
    if lang=='en':
        already=bool(source.article and re.search(rf'\bArticle\s+{re.escape(str(source.article))}\b',title,re.I))
        art=f', Article {source.article}' if source.article and not already else ''
        return f'Legal basis: {title}{art}. [S{i}]'
    nt=normalize_ar(title)
    already=bool(source.article and re.search(rf'الماده\s*{re.escape(str(source.article))}',nt))
    art=f'، المادة {source.article}' if source.article and not already else ''
    return f'الأساس القانوني: {title}{art}. [S{i}]'


def _best_penalty_clause(message: str, sources: list[SourceItem], lang: str):
    terms=_query_terms(message)
    markers=EN_PENALTY_MARKERS if lang=='en' else AR_PENALTY_MARKERS
    candidates=[]
    for i,s in enumerate(sources,1):
        if s.source_kind=='reference':
            continue
        for seg in _segments(s.excerpt):
            low=normalize_ar(seg) if lang=='ar' else seg.lower()
            marker_hits=sum(1 for m in markers if (normalize_ar(m) if lang=='ar' else m.lower()) in low)
            if not marker_hits:
                continue
            overlap=_term_overlap(seg,terms)
            title_overlap=_term_overlap(s.title,terms)
            # The conduct must connect to the clause or its law title. This is what prevents
            # an unrelated amendment about fines from being returned for a question about zina.
            if terms and overlap==0 and title_overlap==0:
                continue
            quant=1.8 if (_has_arabic_number(seg) or any(x in low for x in ('دينار','دنانير','day','year','month'))) else 0.0
            score=s.score + _source_bonus(s) + marker_hits*2.2 + overlap*3.0 + title_overlap*1.2 + quant
            if _looks_garbled(seg):
                score-=3.5
            candidates.append((score,i,s,seg))
    if not candidates:
        return None
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0]


def _best_deadline_clause(message: str, sources: list[SourceItem], lang: str):
    terms=_query_terms(message)
    appeal_markers=EN_APPEAL_MARKERS if lang=='en' else AR_APPEAL_MARKERS
    candidates=[]
    nq=normalize_ar(message) if lang=='ar' else message.lower()
    asks_sharia=lang=='ar' and ('شرعي' in nq or 'شرعيه' in nq)
    asks_default=lang=='ar' and ('غيابي' in nq or 'بمثابه الوجاهي' in nq or 'بمثابة الوجاهي' in message)
    asks_supreme=lang=='ar' and ('العليا الشرعيه' in nq or 'المحكمه العليا' in nq or 'قرار الاستيناف الشرعي' in nq)

    for i,s in enumerate(sources,1):
        if s.source_kind=='reference':
            continue
        segs=_segments(s.excerpt)
        for idx,seg in enumerate(segs):
            low=normalize_ar(seg) if lang=='ar' else seg.lower()
            has_appeal=any((normalize_ar(m) if lang=='ar' else m.lower()) in low for m in appeal_markers)
            duration=_deadline_value_phrase(seg,lang)
            if not (duration and has_appeal):
                continue
            overlap=_term_overlap(seg,terms)
            title_overlap=_term_overlap(s.title,terms)
            score=s.score + _source_bonus(s) + 7.0 + overlap*2.6 + title_overlap*1.2

            title_n=normalize_ar(s.title) if lang=='ar' else s.title.lower()
            if asks_sharia:
                if 'شرعي' in title_n: score+=8.0
                if 'اصول المحاكمات الشرعيه' in title_n: score+=8.0
            if asks_default:
                if 'غيابي' in low: score+=12.0
                else: score-=8.0
                if str(s.article or '')=='112' and 'اصول المحاكمات الشرعيه' in title_n:
                    score+=18.0
            # A question about a first-instance Sharia default judgment is not the same
            # thing as challenging a Sharia Court of Appeal judgment before the Supreme
            # Sharia Court.
            if asks_sharia and not asks_supreme and 'المحكمه العليا الشرعيه' in title_n:
                score-=16.0

            joined=seg
            if idx+1 < len(segs):
                nxt=segs[idx+1]
                nn=normalize_ar(nxt) if lang=='ar' else nxt.lower()
                if any((normalize_ar(x) if lang=='ar' else x) in nn for x in ('تاريخ','تبليغ','اليوم','يبدأ','تبتدئ','تبتديء','يسقط من المدة','from','service','notice')):
                    joined += ' ' + nxt
            candidates.append((score,i,s,joined))
    if not candidates:
        return None
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0]

def _best_points_clause(message: str, sources: list[SourceItem], lang: str):
    if lang!='ar':
        return None
    qn=normalize_ar(message)
    terms=_query_terms(message)
    candidates=[]
    for i,s in enumerate(sources,1):
        if 'نقاط' not in normalize_ar(s.excerpt) and 'نقاط' not in normalize_ar(s.title):
            continue
        text=s.excerpt.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
        ntext=normalize_ar(text)
        # Most important pilot case: red light. Read the table row, not a sentence split.
        if ('اشاره حمراء' in qn or 'اشاره' in qn and 'حمراء' in qn):
            m=re.search(r'تجاوز\s+الاشاره(?:\s+الضوييه)?\s+الحمراء[\.\s،:;-]{0,30}(\d{1,2})',ntext)
            if m:
                points=m.group(1)
                seg=f'تجاوز الإشارة الضوئية الحمراء يسجل {points} نقاط مرورية.'
                candidates.append((s.score+_source_bonus(s)+12.0,i,s,seg))
                continue
        # Generic point question: use a compact window around the first query term.
        overlap=_term_overlap(text,terms)
        if terms and overlap==0:
            continue
        nums=re.findall(r'(?<!\d)(\d{1,2})(?!\d)',text)
        if nums:
            window=_short_rule(text,420)
            candidates.append((s.score+_source_bonus(s)+overlap*2.0,i,s,window))
    if not candidates:
        return None
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0]


def _best_fee_clause(message: str, sources: list[SourceItem], lang: str):
    terms=_query_terms(message)
    candidates=[]
    for i,s in enumerate(sources,1):
        if s.source_kind=='reference':
            continue
        for seg in _segments(s.excerpt):
            n=normalize_ar(seg) if lang=='ar' else seg.lower()
            fee_hit=('رسم' in n or 'رسوم' in n or 'دينار' in n) if lang=='ar' else any(x in n for x in ('fee','fees','jod','dinar'))
            if not fee_hit:
                continue
            if not (_has_arabic_number(seg) or ('دينار' in n if lang=='ar' else 'dinar' in n)):
                continue
            overlap=_term_overlap(seg,terms)
            score=s.score+_source_bonus(s)+5.0+overlap*2.0
            if s.source_kind=='official_service': score+=3.0
            candidates.append((score,i,s,seg))
    if not candidates:
        return None
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0]


def _penalty_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    found=_best_penalty_clause(message,sources,route.language)
    if found:
        _,i,s,seg=found
        nq=normalize_ar(message) if route.language=='ar' else message.lower()
        # Curated article-level facts are deliberately compact and may contain the
        # necessary variants of the same offence. Use the full excerpt instead of
        # dropping important qualifiers after the first sentence.
        if s.source_kind in {'canonical_verified','verified_crosscheck'} and len(s.excerpt or '')<=1500:
            rule=_short_rule(s.excerpt,1450)
        else:
            rule=_short_rule(seg)
        if route.language=='en':
            return GroundedAnswer(f'Penalty: {rule} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'strong')
        tail=''
        if 'سرقه' in nq and str(s.article or '')=='407':
            tail='\n\nمهم: هذه عقوبة صورة السرقة العامة الواردة في المادة 407، وليست عقوبة موحّدة لكل أنواع السرقة. إذا كانت السرقة ليلاً، بالكسر أو الخلع، بسلاح أو عنف، من منزل، أو تعلقت بمركبة، فقد يختلف الوصف والعقوبة.'
        elif 'زنا' in nq and str(s.article or '')=='282':
            tail='\n\nمهم: للملاحقة في جريمة الزنا شروط شكوى ومواعيد خاصة، كما أن الإثبات منظم بنصوص لاحقة؛ لذلك هذه المدة هي العقوبة وليست وحدها كل شروط الملاحقة.'
        elif 'قتل' in nq and str(s.article or '')=='326':
            tail='\n\nمهم: هذا الجواب عن القتل القصد وفق المادة 326 كما ورد في المصدر الرسمي المسترجع. القتل له صور قانونية أخرى وقد تختلف العقوبة باختلاف القصد والظروف المشددة وطريقة وقوع الجريمة؛ إذا وصفت الواقعة أقدر أحدد المسار الأدق.'
        elif ('ابتزاز' in nq or 'يبتز' in nq) and str(s.article or '')=='18':
            tail='\n\nإذا كان التهديد بارتكاب جريمة أو بإسناد أمور خادشة للشرف أو الاعتبار ومصحوباً بطلب صريح أو ضمني، فالمادة نفسها تقرر صورة أشد كما هو مبين في النص المسترجع.'
        return GroundedAnswer(f'العقوبة: {rule} [S{i}]\n\n{_legal_basis(s,i,"ar")}{tail}', 'strong')

    points=_best_points_clause(message,sources,route.language)
    if points:
        _,i,s,seg=points
        if route.language=='ar':
            return GroundedAnswer(
                f'الجزاء المروري المؤكد: {_short_rule(seg,420)} [S{i}]\n\n'
                f'{_legal_basis(s,i,"ar")}\n\n'
                'لم أجد في النص المسترجع لهذه المخالفة قيمة غرامة أو مدة حبس واضحة بما يكفي، لذلك لن أضيف رقماً غير مثبت.',
                'partial'
            )
    return None

def _deadline_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    found=_best_deadline_clause(message,sources,route.language)
    if not found:
        return None
    _,i,s,seg=found
    rule=_short_rule(seg,760)
    if route.language=='en':
        return GroundedAnswer(f'Time limit: {rule} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'strong')
    return GroundedAnswer(f'المدة: {rule} [S{i}]\n\n{_legal_basis(s,i,"ar")}', 'strong')


def _fees_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    found=_best_fee_clause(message,sources,route.language)
    if not found:
        return None
    _,i,s,seg=found
    if route.language=='en':
        return GroundedAnswer(f'Fee: {_short_rule(seg,600)} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'strong')
    return GroundedAnswer(f'الرسوم: {_short_rule(seg,600)} [S{i}]\n\n{_legal_basis(s,i,"ar")}', 'strong')


def _article_answer(route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if not route.article_numbers or not sources:
        return None
    target=route.article_numbers[0]
    for i,s in enumerate(sources,1):
        if str(s.article or '')==str(target) and s.excerpt and s.source_kind!='reference':
            if route.language=='en':
                return GroundedAnswer(f'Article {target}: {_short_rule(s.excerpt,850)} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'strong')
            return GroundedAnswer(f'المادة {target}: {_short_rule(s.excerpt,850)} [S{i}]\n\n{_legal_basis(s,i,"ar")}', 'strong')
    return None


def _cyber_action_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if route.language!='ar' or route.primary_domain!='cyber':
        return None
    nq=normalize_ar(message)
    if not any(normalize_ar(x) in nq for x in ('شو اعمل','شو أعمل','ماذا افعل','ماذا أفعل','تعرضت','ابلاغ','إبلاغ','شكوى','اشتكي','أشتكي')):
        return None
    if not any(normalize_ar(x) in nq for x in ('ابتزاز','تهديد','واتساب','اختراق','جرائم الكترونية','جرائم إلكترونية')):
        return None

    safety=None; contact=None
    for i,s in enumerate(sources,1):
        tn=normalize_ar(s.title)
        ex=normalize_ar(s.excerpt)
        if safety is None and ('ارشادات رسميه' in tn or 'عدم تحويل مبالغ' in ex or 'عدم الرد' in ex):
            safety=(i,s)
        if contact is None and ('وحده مكافحه الجرائم الالكترونيه' in tn or 'ecrimes' in (s.excerpt or '').lower() or 'الرقم المجاني 196' in ex):
            contact=(i,s)
    if not safety and not contact:
        return None

    lines=['الإجراء المقترح من المصادر الرسمية:']
    if safety:
        i,s=safety
        lines.append(f'1. {_short_rule(s.excerpt,500)} [S{i}]')
    if contact:
        i,s=contact
        lines.append(f'2. {_short_rule(s.excerpt,520)} [S{i}]')
    lines.append('3. إذا كان الابتزاز يتضمن طلب مال أو تهديداً بالنشر، لا تدفع ولا تدخل في مساومة طويلة؛ استخدم قنوات الإبلاغ الرسمية الظاهرة أعلاه.')
    return GroundedAnswer('\n'.join(lines), 'strong')


def _termination_rights_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if route.language!='ar' or route.primary_domain!='labor':
        return None
    nq=normalize_ar(message)
    if not any(normalize_ar(x) in nq for x in ('فصلني','طردني','فصل تعسفي','بدون انذار','بدون إنذار','انهاء خدمتي','إنهاء خدمتي','شهر الانذار','شهر الإنذار')):
        return None

    notice=None; arbitrary=None; complaint=None; article31=None
    for i,s in enumerate(sources,1):
        tn=normalize_ar(s.title); ex=normalize_ar(s.excerpt)
        if notice is None and ('بدل الاشعار' in ex or 'فتره الاشعار' in ex) and ('المجلس القضائي' in normalize_ar(s.authority) or s.source_kind=='judicial_principle'):
            notice=(i,s)
        if arbitrary is None and ('نصف شهر' in ex and 'شهرين' in ex and 'فصل' in ex):
            arbitrary=(i,s)
        if complaint is None and ('الشكاوى العماليه' in tn or 'النزاعات العماليه' in ex or '080022208' in (s.excerpt or '')):
            complaint=(i,s)
        if article31 is None and (str(s.article or '')=='31' or 'انهاء او تعليق العقود' in tn):
            article31=(i,s)

    if not any((notice,arbitrary,complaint,article31)):
        return None

    dismissal_claim=any(normalize_ar(x) in nq for x in ('فصلني','طردني','فصل تعسفي','انهاء خدمتي','إنهاء خدمتي','بدون انذار','بدون إنذار'))

    # Carry factual follow-up details into the answer. This is especially important when
    # the assistant previously asked for contract type, service length, dismissal reason
    # and notice, and the user answers in a separate message. The chat layer supplies the
    # recent user turns in `message`; we still ground every legal consequence in sources.
    ascii_message=message.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    years_match=re.search(r'(?<!\d)(\d{1,2})(?!\d)\s*(?:سنوات|سنه|سنة|عام|اعوام|أعوام)',ascii_message)
    service_years=int(years_match.group(1)) if years_match else None
    salary_match=re.search(r'(?:راتبي|اجري|أجري|الراتب|الاجر|الأجر)\s*(?:هو|=|:)??\s*(\d{2,5})(?:\s*دينار)?',ascii_message)
    monthly_wage=float(salary_match.group(1)) if salary_match else None
    indefinite=any(normalize_ar(x) in nq for x in ('غير محدد المده','غير محدد المدة'))
    no_notice=any(normalize_ar(x) in nq for x in ('ما اعطوني','ما أعطوني','ما وصلني اشعار','ما وصلني إشعار','ما استلمت اشعار','ما استلمت إشعار','بدون انذار','بدون إنذار','ولا انذار','ولا إنذار'))
    has_followup_facts=bool(indefinite or service_years or monthly_wage)

    if has_followup_facts and dismissal_claim:
        summary=[]
        if indefinite: summary.append('عقد غير محدد المدة')
        if service_years is not None: summary.append(f'مدة خدمة {service_years} سنوات')
        if no_notice: summary.append('تقول إنك لم تستلم إشعاراً قبل الفصل')
        if monthly_wage is not None: summary.append(f'الأجر الشهري المذكور {monthly_wage:g} دينار')
        parts=['بناءً على التفاصيل التي ذكرتها الآن: ' + '، '.join(summary) + '.']
        if notice:
            i,s=notice
            if no_notice:
                parts.append(f'1. **بدل الإشعار:** عدم وجود إشعار يجعل هذا البند مهماً في تقييم مطالبتك. المبدأ القضائي المنشور يقرر أن إعفاء العامل من العمل خلال فترة الإشعار يلزم صاحب العمل بدفع بدل الإشعار. [S{i}] النص المسترجع عندي هنا لا يثبت طول مدة الإشعار نفسها، لذلك لن أحسب هذا البدل رقمياً من غير نص المادة النافذ.')
            else:
                parts.append(f'1. **بدل الإشعار:** المبدأ القضائي المنشور يقرر أن إعفاء العامل من العمل خلال فترة الإشعار يلزم صاحب العمل بدفع بدل الإشعار. [S{i}]')
        if arbitrary:
            i,s=arbitrary
            if service_years is not None:
                months=max(service_years*0.5,2.0)
                months_text=f'{months:g}'
                calc=f'نصف شهر × {service_years} سنوات = {service_years*0.5:g} شهر، ومع الحد الأدنى المذكور تكون النتيجة {months_text} شهر من الأجر'
                if monthly_wage is not None:
                    amount=monthly_wage*months
                    calc+=f'، أي نحو {amount:g} دينار وفق هذه الصيغة وحدها'
                parts.append(f'2. **الفصل التعسفي إذا ثبت:** التوضيح الرسمي لوزارة العمل يذكر نصف شهر عن كل سنة خدمة وبحد أدنى أجر شهرين. [S{i}] بناءً على مدة الخدمة التي ذكرتها، {calc}. هذا ليس حكماً نهائياً بأن الفصل تعسفي؛ ثبوت التعسف يعتمد على سبب الإنهاء والوقائع.')
            else:
                parts.append(f'2. **الفصل التعسفي إذا ثبت:** التوضيح الرسمي لوزارة العمل يذكر نصف شهر عن كل سنة خدمة وبحد أدنى أجر شهرين. [S{i}]')
        missing=[]
        if not service_years: missing.append('مدة الخدمة')
        if not indefinite: missing.append('نوع العقد')
        if not no_notice: missing.append('هل وصلك إشعار خطي ومتى')
        # The dismissal reason remains legally decisive even after the other three facts are supplied.
        missing.append('السبب الذي ذكره صاحب العمل للفصل')
        if monthly_wage is None: missing.append('راتبك الشهري إذا بدك أحسب قيمة تقديرية للاستحقاق المذكور')
        parts.append('حتى أكمل التقييم على حالتك نفسها، بقي عندي: ' + '، '.join(dict.fromkeys(missing)) + '.')
        if complaint:
            i,s=complaint
            parts.append(f'وللنزاع أو الاستفسار العمالي، تظهر في المصدر الرسمي قنوات وزارة العمل ومنها مركز الاتصال الوطني 06/5008080 والخط المجاني 080022208. [S{i}]')
        return GroundedAnswer('\n\n'.join(parts), 'strong' if notice and arbitrary else 'partial')

    parts=['حقوقك المحتملة التي أقدر أثبت أساسها من المصادر الرسمية المسترجعة:']
    if notice:
        i,s=notice
        parts.append(f'1. **بدل الإشعار:** إذا كان الإشعار واجباً في حالتك، فمبدأ قضائي منشور من المجلس القضائي يقرر أن إعفاء صاحب العمل للعامل من العمل خلال فترة الإشعار يلزم صاحب العمل بدفع بدل الإشعار. [S{i}]')
    if arbitrary and dismissal_claim:
        i,s=arbitrary
        parts.append(f'2. **تعويض الفصل التعسفي:** في توضيح رسمي منشور لوزارة العمل، ذكرت الوزارة أن قانون العمل يقرر للعامل نصف شهر عن كل سنة خدمة، بما لا يقل عن أجر شهرين، إذا ثبت أن الفصل كان تعسفياً. [S{i}]')
        parts.append('هذا التوضيح يساعد على تحديد نوع الحق، لكن احتساب الاستحقاق النهائي يتطلب تطبيق النص النافذ على عقدك ووقائع الفصل؛ لذلك لا أحسب مبلغاً نهائياً قبل معرفة تفاصيل العقد والخدمة.')

    if dismissal_claim:
        parts.append('حتى أحدد حقك بدقة، جاوبني على 4 نقاط: هل عقدك **محدد المدة أم غير محدد**؟ كم مدة خدمتك؟ ما السبب الذي ذكره صاحب العمل للفصل؟ وهل استلمت إشعاراً خطياً، ومتى؟')

    # Article 31 is not a generic dismissal rule. Surface it only where the user's facts suggest
    # economic/technical restructuring or a collective shutdown/suspension scenario.
    economic=any(normalize_ar(x) in nq for x in ('اغلاق','إغلاق','توقف المنشأه','توقف المنشأة','ظروف اقتصاديه','ظروف اقتصادية','تقليص','اعاده هيكله','إعادة هيكلة','تعليق العقود'))
    if article31 and economic:
        i,s=article31
        parts.append(f'إذا كان الإنهاء بسبب ظروف اقتصادية/فنية أو توقف يستدعي إنهاء أو تعليق عقود غير محددة المدة، فهناك إجراءات خاصة مرتبطة بالمادة 31 لدى وزارة العمل. [S{i}]')
    if complaint:
        i,s=complaint
        parts.append(f'وللنزاع أو الاستفسار العمالي، تظهر في المصدر الرسمي قنوات وزارة العمل ومنها مركز الاتصال الوطني 06/5008080 والخط المجاني 080022208. [S{i}]')

    strength='strong' if notice and (arbitrary or not dismissal_claim) else 'partial'
    return GroundedAnswer('\n\n'.join(parts), strength)


def _procedure_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if not sources:
        return None
    terms=_query_terms(message)
    best=None
    procedure_words=(
        'تقديم','لائحة','المحكمة','قلم','كاتب','رسوم','شكوى','المدعي العام','الادعاء العام','النيابة',
        'حضور','الاختصاص','صاحب العلاقة','الممثل القانوني','إلكترونياً','الكترونيا','ورقياً','ورقيا',
    )
    for i,s in enumerate(sources,1):
        if s.source_kind=='reference':
            continue
        segs=_segments(s.excerpt)
        selected=[]
        for seg in segs:
            n=normalize_ar(seg)
            if any(normalize_ar(w) in n for w in procedure_words):
                selected.append(seg)
            if len(selected)>=4:
                break
        if selected:
            selected=_dedupe_similar_texts(selected)[:3]
            joined=' '.join(selected)
            score=s.score+_source_bonus(s)+_term_overlap(joined,terms)*2.4
            if s.source_kind=='official_service': score+=3.5
            nq=normalize_ar(message)
            if ('مدعي العام' in nq or 'ادعاء العام' in nq or 'شكوى' in nq) and ('شكوى' in normalize_ar(s.title) or 'ادعاء' in normalize_ar(s.title)):
                score+=8.0
            if route.primary_domain=='cyber' and any(x in nq for x in ('ابتزاز','واتساب','تهديد')):
                st=normalize_ar(s.title)
                if 'وحده مكافحه الجرائم الالكترونيه' in st or 'ارشادات رسميه' in st:
                    score+=10.0
            if _looks_garbled(joined): score-=4.0
            if best is None or score>best[0]:
                best=(score,i,s,selected)
    if not best:
        return None
    _,i,s,segs=best
    text=' '.join(_short_rule(x,300) for x in segs)
    if route.language=='en':
        return GroundedAnswer(f'Procedure: {text} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'partial')
    return GroundedAnswer(f'الإجراء: {text} [S{i}]\n\n{_legal_basis(s,i,"ar")}', 'partial')


def _judgment_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    """Answer finality/judgment-status only when the retrieved text actually states the rule."""
    terms=_query_terms(message)
    # A bare question like "when does a judgment become final?" has no single universal
    # answer. Require case context before attaching a specific finality rule to the user.
    if not terms:
        return None
    candidates=[]
    for i,s in enumerate(sources,1):
        if s.source_kind=='reference': continue
        for seg in _segments(s.excerpt):
            n=normalize_ar(seg)
            if not any(x in n for x in ('الدرجه القطعيه','قطعي','نهائي','قابل للطعن','غير قابل للطعن','اكتسب الحكم')):
                continue
            overlap=_term_overlap(seg,terms)
            score=s.score+_source_bonus(s)+5.0+overlap*2.0
            candidates.append((score,i,s,seg))
    if not candidates:
        return None
    candidates.sort(key=lambda x:x[0],reverse=True)
    _,i,s,seg=candidates[0]
    if route.language=='en':
        return GroundedAnswer(f'Judgment status: {_short_rule(seg,700)} [S{i}]\n\n{_legal_basis(s,i,"en")}', 'partial')
    return GroundedAnswer(f'حالة الحكم: {_short_rule(seg,700)} [S{i}]\n\n{_legal_basis(s,i,"ar")}', 'partial')


def _rights_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if not sources:
        return None
    terms=_query_terms(message)
    candidates=[]
    rights_words=('الحق','يحق','يستحق','أجر','اجر','اجازة','إجازة','تعويض','ساعات العمل','ضمان اجتماعي','إنهاء','انهاء','العامل','صاحب العمل')
    for i,s in enumerate(sources,1):
        if s.source_kind=='reference':
            continue
        for seg in _segments(s.excerpt):
            n=normalize_ar(seg)
            if 'يعتمد قانوني هذا المصدر' in n:
                continue
            hits=sum(1 for w in rights_words if normalize_ar(w) in n)
            if not hits:
                continue
            overlap=_term_overlap(seg,terms)
            score=s.score+_source_bonus(s)+hits+overlap*2.1
            if s.source_kind=='official_guidance': score+=3.5
            if _looks_garbled(seg): score-=5.0
            candidates.append((score,i,s,seg))
    if not candidates:
        return None
    # If clean official service/guidance facts exist, do not let a broken PDF text layer
    # pollute the user-facing rights answer.
    curated=[c for c in candidates if c[2].source_kind in {'official_guidance','official_service'}]
    if curated:
        candidates=curated
    candidates.sort(key=lambda x:x[0],reverse=True)
    picked=[]; seen_texts=[]
    for _,i,s,seg in candidates:
        clean=_short_rule(seg,390)
        if not _dedupe_similar_texts(seen_texts+[clean]) or len(_dedupe_similar_texts(seen_texts+[clean]))==len(seen_texts):
            continue
        seen_texts.append(clean)
        picked.append((i,s,clean))
        if len(picked)>=3:
            break
    if not picked:
        return None
    if route.language=='en':
        body='\n'.join(f'- {seg} [S{i}]' for i,_,seg in picked)
        return GroundedAnswer(f'Verified rights/points from the retrieved official material:\n{body}', 'partial')
    body='\n'.join(f'- {seg} [S{i}]' for i,_,seg in picked)
    tail=''
    nq=normalize_ar(message)
    if any(x in nq for x in ('فصلني','طردني','بدون انذار','فصل تعسفي')):
        tail='\n\nمهم: هذه النقاط لا تكفي وحدها لتحديد تعويض الفصل أو بدل الإشعار في حالتك؛ ذلك يعتمد على نوع العقد وسبب الإنهاء ووقائعه، ولن أحدد مبلغاً غير مثبت من النص المسترجع.'
    return GroundedAnswer(f'الحقوق والنقاط التي أقدر أثبتها من المصادر الرسمية المسترجعة:\n{body}{tail}', 'partial')


def _law_overview_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    if route.language!='ar' or not sources:
        return None
    domain=route.primary_domain
    profiles={
        'labor': ('قانون العمل الأردني','قانون العمل رقم 8 لسنة 1996 وتعديلاته وملحقاته','علاقة العامل بصاحب العمل، الأجور، ساعات العمل، الإجازات، إنهاء الخدمة وحقوق العمل'),
        'traffic': ('قانون السير الأردني','قانون السير رقم 49 لسنة 2008 وتعديلاته','المخالفات المرورية، الترخيص، مسؤوليات السائق والمركبة، وتتكامل بعض المخالفات مع نظام النقاط المرورية'),
        'criminal': ('قانون العقوبات الأردني','قانون العقوبات رقم 16 لسنة 1960 وتعديلاته','الجرائم والعقوبات، مع اختلاف الحكم حسب الوصف القانوني والظروف المشددة أو المخففة'),
        'civil': ('القانون المدني الأردني','القانون المدني رقم 43 لسنة 1976 وتعديلاته','العقود والالتزامات والتعويض والديون والحقوق المدنية'),
        'commercial': ('قانون الشركات الأردني','قانون الشركات رقم 22 لسنة 1997 وتعديلاته','تأسيس الشركات وإدارتها ومسؤولية الشركاء والتحولات والاندماج والتصفية'),
        'personal_status': ('قانون الأحوال الشخصية الأردني','قانون الأحوال الشخصية رقم 15 لسنة 2019','الزواج والطلاق والنفقة والحضانة والإرث والمسائل الأسرية الشرعية'),
        'cyber': ('قانون الجرائم الإلكترونية الأردني','قانون الجرائم الإلكترونية رقم 17 لسنة 2023','الجرائم المرتكبة باستخدام الشبكات وأنظمة المعلومات ووسائل تقنية المعلومات، ومنها صور الابتزاز والتهديد الإلكتروني'),
    }
    if domain not in profiles:
        return None
    heading,law_title,scope=profiles[domain]
    # Prefer a clean curated/canonical source, but a matching official law record is enough
    # for an overview because we do not quote its scraped body.
    candidates=[]
    target=normalize_ar(law_title)
    for i,s in enumerate(sources,1):
        tn=normalize_ar(s.title)
        score=_source_bonus(s)+s.score
        if target in tn or tn in target: score+=12
        if s.source_kind in {'official_guidance','official_service','canonical_verified','verified_crosscheck'}: score+=4
        candidates.append((score,i,s))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates: return None
    _,i,s=candidates[0]
    return GroundedAnswer(
        f'{heading}: {law_title}. [S{i}]\n\n'
        f'بشكل عملي، يغطي {scope}.\n\n'
        'إذا بدك جواباً محدداً، اكتب الحالة نفسها أو رقم المادة؛ مثلاً: «فصلني صاحب العمل بدون إنذار» أو «ما مدة الاستئناف؟».\n\n'
        f'{_legal_basis(s,i,"ar")}',
        'strong'
    )


def generate_grounded_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> GroundedAnswer|None:
    """Return a direct evidence-grounded answer for extractable legal values."""
    article=_article_answer(route,sources)
    if article:
        return article
    if route.intent=='law_overview':
        return _law_overview_answer(message,route,sources)
    if route.intent=='penalty':
        return _penalty_answer(message,route,sources)
    if route.intent in {'deadline','appeal_deadline'}:
        return _deadline_answer(message,route,sources)
    if route.intent=='fees':
        return _fees_answer(message,route,sources)
    if route.intent=='judgment':
        return _judgment_answer(message,route,sources)
    if route.intent in {'procedure','appeal','complaint','enforcement'}:
        cyber=_cyber_action_answer(message,route,sources)
        if cyber: return cyber
        nq=normalize_ar(message)
        if any(normalize_ar(x) in nq for x in ('كم يوم','قديش','مدة','مهلة','خلال كم','deadline','how long')):
            d=_deadline_answer(message,route,sources)
            if d: return d
        return _procedure_answer(message,route,sources)
    if route.intent=='rights':
        termination=_termination_rights_answer(message,route,sources)
        if termination: return termination
        return _rights_answer(message,route,sources)
    return None


def insufficient_answer(message: str, route: RouteResult, sources: list[SourceItem]) -> str:
    """Intent-aware no-guess response. Never substitute a list of sources for the requested value."""
    if route.language=='en':
        if route.intent=='penalty':
            return ('I found the official legal reference, but the retrieved text does not contain a sufficiently clear current penalty for this exact conduct. '
                    'I will not invent a fine, prison term, or article number.')
        if route.intent in {'deadline','appeal_deadline'}:
            return ('I cannot state the exact time limit from the retrieved official text. It can depend on the case type, court, judgment type, and service date/method, so I will not guess.')
        if route.intent=='fees':
            return 'I cannot state the exact filing fee from the retrieved official text, so I will not guess an amount.'
        if route.intent=='judgment':
            return 'The retrieved official text is not specific enough to determine when this judgment becomes final. The answer depends on the judgment and available appeal route.'
        return 'The retrieved official material is not specific enough for a reliable direct answer. I will not fill the gap with an unsupported rule.'

    if route.intent=='penalty':
        return ('لقيت المرجع الرسمي المرتبط بالموضوع، لكن النص المسترجع لا يحتوي عقوبة حالية واضحة وكافية لهذه الحالة بالذات. '
                'لذلك لن أخترع غرامة أو مدة حبس أو رقم مادة. المصادر الظاهرة تساعدك على التحقق، لكن وجود اسم القانون وحده ليس جواباً عن العقوبة.')
    if route.intent in {'deadline','appeal_deadline'}:
        ds=set(route.domains)
        if 'criminal' in ds:
            return ('مدة الاستئناف الجزائي ليست رقماً واحداً لكل الأحكام. حتى أحددها صح، لازم أعرف المحكمة التي أصدرت الحكم (صلح أم بداية/جنايات بحسب الحالة)، ونوع الحكم وهل جرى تبليغه. اذكر هذه التفاصيل ولن أخمّن بمدة من رقم قانون أو سنة تشريع.')
        if 'civil' in ds:
            return ('مدة الاستئناف الحقوقي/المدني قد تختلف حسب المحكمة ونوع الحكم وطريقة التبليغ. حدّد هل الحكم صادر عن صلح حقوق أم بداية حقوق، وهل هو وجاهي أم غيابي/بمثابة الوجاهي، وتاريخ التبليغ، حتى أعطيك المدة الصحيحة.')
        return ('ما بقدر أحدد مدة الطعن أو الاستئناف بدقة من النص الرسمي المسترجع حالياً. المدة قد تختلف حسب نوع القضية والمحكمة ونوع الحكم وتاريخ وطريقة التبليغ، لذلك لن أخمّن بها.')
    if route.intent=='fees':
        return 'ما بقدر أحدد مقدار الرسوم بدقة من النص الرسمي المسترجع حالياً، لذلك لن أخمّن بمبلغ.'
    if route.intent=='judgment':
        return ('ما بقدر أجزم متى يصبح هذا الحكم قطعياً من الأدلة المسترجعة فقط. القطعية ترتبط بنوع الحكم وطريق الطعن المتاح والمدة والتبليغ، ولن أختصرها بقاعدة غير مثبتة.')
    if route.intent=='rights':
        return ('فاهم إنك بدك تعرف حقك مباشرة، لكن الأدلة الرسمية المسترجعة لهذه الحالة لا تكفي حتى أحدد الاستحقاق أو التعويض بدقة. بعرض لك ما هو مثبت من غير ما أضيف حق غير موثق.')
    if route.intent in {'procedure','appeal','complaint','enforcement'}:
        return ('المصادر الرسمية المسترجعة لا تكفي حتى أعطيك الإجراء الكامل بثقة. إذا كانت الخطوة أو المدة غير مثبتة في النص، أوضح النقص بدل التخمين.')
    return 'المادة الرسمية المسترجعة غير كافية لجواب قانوني مباشر وموثوق، لذلك لن أخمّن.'

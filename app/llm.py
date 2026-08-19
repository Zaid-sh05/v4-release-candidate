from __future__ import annotations
from .config import settings
from .models import RouteResult, SourceItem
from .router import DOMAIN_LABELS
from .text import strip_emoji_style

SYSTEM_AR = '''أنت قانوني | Qanoni، مساعد قانوني متخصص في القانون الأردني.
أسلوبك إنساني، هادئ، مهني، واضح، ومحترم. تحدث بالعربية الطبيعية القريبة من المستخدم الأردني من دون مبالغة في العامية.

قواعد ملزمة:
- لا تستخدم أي إيموجي أو رموز تعبيرية تحت أي ظرف.
- لا تقل للمستخدم كلمات تقنية داخلية مثل MCP أو RAG أو embedding أو confidence إلا إذا سأل عنها تقنياً.
- اعتمد فقط على النصوص والمصادر الرسمية التي أُرسلت لك في السياق. لا تخترع مادة أو عقوبة أو غرامة أو مهلة أو رقم قانون.
- إذا لم تكفِ المصادر للإجابة، قل ذلك بوضوح، واذكر ما يلزم التحقق منه بدل التخمين.
- إذا وجدت قانوناً أساسياً وتعديلاً لاحقاً، ميّز بينهما ولا تفترض أن التعديل يحتوي النص الموحّد الكامل.
- ضع الإحالات [S1] و[S2] بجانب الجملة التي تدعمها.
- ابدأ بخلاصة عملية مباشرة، ثم الأساس القانوني، ثم الخطوة العملية التالية عند الحاجة.
- إذا سأل المستخدم عن عقوبة وكانت العقوبة موجودة في الدليل، يجب أن تبدأ الإجابة بـ: العقوبة: ثم تذكر الحبس/الغرامة/الجزاء كما ورد، وليس مجرد عرض المصادر.
- إذا سأل عن مدة استئناف أو طعن وكانت المدة موجودة، ابدأ بـ: المدة: ثم اذكر عدد الأيام ونقطة بدء احتسابها إن كانت مثبتة.
- إذا سأل عن الرسوم وكانت القيمة موجودة، ابدأ بـ: الرسوم: ثم اذكر المبلغ والحالة التي ينطبق عليها.
- إذا سأل متى يصبح الحكم قطعياً، لا تعط قاعدة عامة من عندك؛ اذكر الشرط المثبت أو قل إن نوع الحكم وطريق الطعن والتبليغ يلزم تحديدها.
- إذا سأل عن إجراء، أعطه الخطوات العملية المثبتة قبل التفاصيل العامة.
- إذا سأل عن الحقوق، اذكر الحقوق أو الاستحقاقات المثبتة مباشرة.
- لا تتنبأ بنتيجة المحكمة ولا تقدّم ضماناً قانونياً.
- لا تكرر التنبيه القانوني داخل كل فقرة؛ يكفي الجواب الطبيعي وسيظهر التنبيه في الواجهة.
- إذا كان السؤال محادثة عادية، جاوب كمساعد طبيعي ولا تحوله إلى بحث قانوني.
'''

SYSTEM_EN = '''You are Qanoni, a Jordanian-law AI assistant. Your tone is natural, calm, professional, practical and respectful.
Mandatory rules:
- Never use emojis or emoticons.
- Do not expose internal implementation terms such as MCP, RAG, embeddings, or confidence unless the user asks a technical question.
- Use only the official-source excerpts provided in context. Never invent an article, penalty, fine, deadline, or law number.
- If the evidence is insufficient, say so plainly and identify what needs verification.
- Distinguish a base law from later amendments; do not treat an amendment as the full consolidated law.
- Cite supported claims inline as [S1], [S2].
- Lead with a practical answer, then legal basis, then next step where useful.
- If the user asks for a penalty and it appears in the evidence, begin with 'Penalty:' and state it directly.
- If the user asks for an appeal/deadline and the time limit appears in evidence, begin with 'Time limit:' and state the number and trigger date if supported.
- If the user asks for fees and the amount appears in evidence, begin with 'Fee:' and state the amount and applicable situation.
- If the user asks when a judgment becomes final, do not generalize; state only the supported condition or explain which judgment/appeal/service facts are missing.
- If the user asks for procedure, give the supported steps first.
- Do not promise court outcomes.
'''


def _source_context(sources:list[SourceItem]) -> str:
    blocks=[]
    for i,s in enumerate(sources,1):
        blocks.append(f'''[S{i}] {s.title}\nAuthority: {s.authority}\nDomain: {s.domain}\nLaw number: {s.law_number or '-'}\nYear: {s.year or '-'}\nArticle: {s.article or '-'}\nOfficial URL: {s.source_url}\nExcerpt:\n{s.excerpt}''')
    return '\n\n'.join(blocks)


def _history_text(history:list[dict]) -> str:
    return '\n'.join(f"{m['role']}: {m['content'][:1800]}" for m in history[-6:])


def generate_answer(message:str, route:RouteResult, sources:list[SourceItem], history:list[dict]) -> str|None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        client=OpenAI(api_key=settings.openai_api_key)
        labels=[DOMAIN_LABELS.get(d,{}).get(route.language,d) for d in route.domains]
        prompt=f'''Conversation context:\n{_history_text(history) or '(new conversation)'}\n\nUser question:\n{message}\n\nLegal routing hint: {', '.join(labels)}\nIntent: {route.intent}\n\nOfficial retrieved evidence:\n{_source_context(sources) or 'No official excerpt was retrieved.'}'''
        response=client.responses.create(model=settings.openai_model,instructions=SYSTEM_AR if route.language=='ar' else SYSTEM_EN,input=prompt)
        text=strip_emoji_style((response.output_text or '').strip())
        return text or None
    except Exception:
        return None


def embed_query(text:str) -> list[float]|None:
    if not settings.openai_api_key: return None
    try:
        from openai import OpenAI
        client=OpenAI(api_key=settings.openai_api_key)
        r=client.embeddings.create(model=settings.openai_embedding_model,input=text)
        return r.data[0].embedding
    except Exception:
        return None

/* Qanoni V4 grounded feedback review UI.
   Loaded after app.js and intentionally overrides only sendFeedback(). */

function feedbackCopy(key){
  const ar={
    notePlaceholder:'اختياري: شو كان غلط أو ناقص بالإجابة؟',
    send:'إرسال للمراجعة',
    cancel:'إلغاء',
    checking:'جارٍ مراجعة الإجابة من المصادر الرسمية...',
    corrected:'تمت مراجعة الإجابة وتصحيحها من المصادر الرسمية.',
    queued:'تم تسجيل الملاحظة. لم يجد النظام تصحيحاً رسمياً قوياً بما يكفي، فتم إبقاؤها للمراجعة بدون تخمين.',
    saved:'تم تسجيل ملاحظتك.',
    failed:'تعذر إرسال الملاحظة. حاول مرة ثانية.'
  };
  const en={
    notePlaceholder:'Optional: what was wrong or missing from this answer?',
    send:'Send for review',
    cancel:'Cancel',
    checking:'Re-checking the answer against official sources...',
    corrected:'The answer was re-checked and corrected from official sources.',
    queued:'Feedback saved. No strong official correction was found, so it was kept for review without guessing.',
    saved:'Feedback saved.',
    failed:'Could not send feedback. Please try again.'
  };
  return (state.lang==='ar'?ar:en)[key]||key;
}

function feedbackStatus(row,text,kind=''){
  let el=row.querySelector('.feedback-review-status');
  if(!el){el=document.createElement('span');el.className='feedback-review-status';row.appendChild(el)}
  el.className=`feedback-review-status ${kind}`.trim();
  el.textContent=text;
}

function closeFeedbackEditor(row){
  const editor=row.querySelector('.feedback-review-editor');
  if(editor)editor.remove();
}

function openFeedbackEditor(row){
  if(row.dataset.sent||row.querySelector('.feedback-review-editor'))return;
  const editor=document.createElement('div');
  editor.className='feedback-review-editor';
  const input=document.createElement('textarea');
  input.rows=2;input.maxLength=1200;input.placeholder=feedbackCopy('notePlaceholder');
  const actions=document.createElement('div');actions.className='feedback-review-actions';
  const submit=document.createElement('button');submit.type='button';submit.className='feedback-review-submit';submit.textContent=feedbackCopy('send');
  const cancel=document.createElement('button');cancel.type='button';cancel.className='feedback-review-cancel';cancel.textContent=feedbackCopy('cancel');
  actions.append(submit,cancel);editor.append(input,actions);row.appendChild(editor);
  cancel.onclick=()=>closeFeedbackEditor(row);
  submit.onclick=()=>submitFeedbackReview('not_helpful',row,input.value);
  input.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();submit.click()}
  });
  input.focus();
}

async function submitFeedbackReview(rating,row,note=''){
  if(!state.conversationId||row.dataset.sent)return;
  row.dataset.sent='1';
  row.querySelectorAll('button').forEach(b=>b.disabled=true);
  closeFeedbackEditor(row);
  if(rating==='not_helpful')feedbackStatus(row,feedbackCopy('checking'),'checking');
  try{
    const response=await fetch('/api/feedback',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({conversation_id:state.conversationId,rating,note:note||null})
    });
    if(!response.ok)throw new Error(await response.text());
    const data=await response.json();
    const review=data.review;
    if(rating==='not_helpful'&&review){
      if(review.status==='auto_corrected'&&review.proposed_answer){
        feedbackStatus(row,feedbackCopy('corrected'),'corrected');
        appendMessage('assistant',review.proposed_answer,review.domain?[review.domain]:[]);
        if(Array.isArray(review.sources)&&review.sources.length)renderEvidence(review.sources);
      }else{
        feedbackStatus(row,feedbackCopy('queued'),'queued');
      }
    }else{
      feedbackStatus(row,feedbackCopy('saved'),'saved');
    }
  }catch(error){
    row.dataset.sent='';
    row.querySelectorAll('button').forEach(b=>b.disabled=false);
    feedbackStatus(row,feedbackCopy('failed'),'error');
    console.error(error);
  }
}

// Existing message buttons call this global function. Helpful stays one-click;
// negative feedback gets an optional note before the official-source re-check.
sendFeedback=async function(rating,row){
  if(rating==='not_helpful'){
    openFeedbackEditor(row);
    return;
  }
  return submitFeedbackReview(rating,row,'');
};

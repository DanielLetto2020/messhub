/* Общие мелочи для всех страниц messhub: экранирование, запросы к API, буфер обмена.
   Раньше esc(), attr(), escRe(), api() и copyText() были скопированы в каждую страницу
   (widget, settings, assistant, message, find) — правка в одном месте расходилась с остальными.
   Подключается везде рядом с i18n.js:  <script src="/common.js"></script>
   Страница может переопределить любую функцию ниже своей копией - тогда её версия победит
   (в widget.html и settings.html свой toast: с кнопкой действия и со своим классом). */

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
const attr = s => esc(s).replace(/"/g,'&quot;');
function escRe(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}

/* Запрос к локальному API. Сессионный токен подставляет браузер сам: cookie ставит сервер
   при отдаче страницы, а скрипты и curl передают его заголовком X-Messhub-Token
   (см. app/session.py). credentials:'same-origin' нужен, чтобы cookie ушла с запросом. */
async function api(path, body){
  const r = await fetch(path, {credentials:'same-origin',
    ...(body===undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'},
                                 body:JSON.stringify(body)})});
  let d=null; try{d=await r.json();}catch(e){}
  if(!r.ok) throw new Error((d&&d.error)||t('Сервер ответил {c}',{c:r.status}));
  return d;
}

/* То же для случаев, где тела нет: ответ всегда JSON, поэтому здесь без разбора тела ошибки. */
async function post(path, body){
  const r = await fetch(path, {method:'POST', credentials:'same-origin',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if(!r.ok) throw new Error('HTTP '+r.status);
  return r.json();
}

/* Копирование в буфер: буфер обмена может быть запрещён, тогда - через скрытое поле. */
async function copyText(s){
  try{await navigator.clipboard.writeText(s);return true;}
  catch(e){
    const ta=document.createElement('textarea'); ta.value=s; ta.style.cssText='position:fixed;opacity:0';
    document.body.appendChild(ta); ta.select();
    let ok=false; try{ok=document.execCommand('copy');}catch(_){}
    ta.remove(); return ok;
  }
}

/* Кнопка с подтверждением вторым кликом (удалить, восстановить, заменить ключ).
   Текст кнопки (не разметка) — как в settings.html и assistant.html. */
function confirmBtn(b, ask, run){
  let armed=0; const orig=b.textContent;
  b.onclick=async e=>{
    if(e) e.stopPropagation();
    if(!b.classList.contains('confirm')){
      b.classList.add('confirm'); b.textContent=ask;
      armed=setTimeout(()=>{b.classList.remove('confirm');b.textContent=orig;},4000);
      return;
    }
    clearTimeout(armed); b.classList.remove('confirm'); b.textContent=orig;
    await run();
  };
}

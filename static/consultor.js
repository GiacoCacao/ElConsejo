// El Consejo — Consultor general: asesor interno, fuera del hemiciclo, que aclara palabras y conceptos.
const CONS_CLAVE = 'consultor.historial';
let consHist = JSON.parse(localStorage[CONS_CLAVE] || '[]'), consCtx = '', consOcupado = false;
const consGuardar = () => { localStorage[CONS_CLAVE] = JSON.stringify(consHist.slice(-40)); };

function consAbrir(termino, contexto) {
  const dlg = $('#consultor');
  const sobreModal = !!document.querySelector('dialog[open]:not(#consultor):modal');
  if (dlg.open && dlg.matches(':modal') !== sobreModal) dlg.close();   // encima de un acta o una votación: modal
  if (!dlg.open) sobreModal ? dlg.showModal() : dlg.show();
  $('#lateral').hidden = true;
  consCtx = contexto || '';
  pintarConsCtx();
  consPintar();
  if (termino) { $('#consPregunta').value = termino; consPreguntar(); }
  else $('#consPregunta').focus();
}
function pintarConsCtx() {
  const c = $('#consCtx');
  c.hidden = !consCtx;
  c.innerHTML = consCtx ? `<span>«${esc(consCtx)}»</span><button type="button" aria-label="Quitar el pasaje">${ico('x')}</button>` : '';
  if (consCtx) c.querySelector('button').onclick = () => { consCtx = ''; pintarConsCtx(); };
}
function consPintar() {
  const box = $('#consHist');
  if (!consHist.length) {
    box.innerHTML = `<div class="cons-vacio">${ORNAMENTO}<p>Pregunte por el significado de una palabra, una sigla o un concepto.</p>
      <small>El consultor no participa en el debate ni opina sobre el asunto: solo aclara. También puede <b>seleccionar un término</b>
      en cualquier respuesta, transcripción o acta y pulsar «Consultar».</small></div>`;
    return;
  }
  box.innerHTML = consHist.map((h, i) => `<div class="cons-item" data-i="${i}">
      <div class="pq"><b>${esc(h.p)}</b>${h.ctx ? `<em>«${esc(h.ctx.slice(0, 160))}${h.ctx.length > 160 ? '…' : ''}»</em>` : ''}</div>
      <div class="rs ${h.error ? 'error' : ''}"><div class="cuerpo">${h.r ? md(h.r) : h.error ? esc(h.error) : '<div class="pensando-txt">Consultando<span class="puntos"><i></i><i></i><i></i></span></div>'}</div></div>
      <div class="hora">${h.panel ? esc(h.panel) + ' · ' : ''}${new Date(h.ts).toLocaleString('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div></div>`).join('');
  box.scrollTop = box.scrollHeight;
}
async function consPreguntar() {
  const p = $('#consPregunta').value.trim();
  if (!p || consOcupado) return;
  consOcupado = true; $('#consEnviar').disabled = true; $('#consPregunta').value = '';
  const item = { p, ctx: consCtx, r: '', ts: Date.now(), panel: panel ? panel.nombre : '' };
  consHist.push(item); consCtx = ''; pintarConsCtx(); consPintar();
  const caja = () => $(`#consHist [data-i="${consHist.indexOf(item)}"] .cuerpo`);
  let raf = 0;
  try {
    const fin = await flujo('/api/consultor', x => {
      item.r += x;
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; const c = caja(); if (c) { c.innerHTML = md(item.r); $('#consHist').scrollTop = $('#consHist').scrollHeight; } });
    }, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pregunta: p, contexto: item.ctx, panel_id: panel && panel.id }) });
    item.r = fin.texto || item.r;
    if (fin.error) item.error = fin.error;
  } catch (e) { item.error = e.message; }
  consGuardar(); consPintar(); pedirConsumo();
  consOcupado = false; $('#consEnviar').disabled = false; $('#consPregunta').focus();
}
$('#consForm').onsubmit = e => { e.preventDefault(); consPreguntar(); };
$('#abrirConsultor').onclick = () => consAbrir();
$('#cerrarConsultor').onclick = () => $('#consultor').close();
$('#consultor').addEventListener('click', e => { if (e.target === $('#consultor')) $('#consultor').close(); });   // clic en el fondo
$('#consLimpiar').onclick = async () => {
  if (!consHist.length || !await confirmar('¿Borrar el historial del consultor en este navegador?', 'Borrar')) return;
  consHist = []; consGuardar(); consPintar();
};

// ---- seleccionar un término en una respuesta, la transcripción o un acta ----
const ZONAS = '#respuesta, #registro, #actaDoc, #vCuerpo, #consHist';
function selTermino() {
  const s = window.getSelection();
  const t = s && s.rangeCount ? s.toString().replace(/\s+/g, ' ').trim() : '';
  if (t.length < 2 || t.length > 80) return null;
  const nodo = s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
  if (!nodo || !nodo.closest(ZONAS)) return null;
  const bloque = nodo.closest('p, li, blockquote, h2, h3, h4, .cuerpo') || nodo;
  return { termino: t, contexto: bloque.textContent.replace(/\s+/g, ' ').trim().slice(0, 600), rect: s.getRangeAt(0).getBoundingClientRect() };
}
document.addEventListener('mouseup', e => {
  if (e.target.closest('#consSel')) return;
  setTimeout(() => {
    const b = $('#consSel'), sel = selTermino();
    if (!sel || document.body.classList.contains('observador')) { b.hidden = true; return; }
    const destino = document.querySelector('dialog[open]:modal:not(#consultor)') || document.querySelector('#consultor[open]:modal') || document.body;
    if (b.parentElement !== destino) destino.append(b);   // dentro del diálogo abierto para quedar encima
    b.innerHTML = `${ico('lupa')} Consultar «${esc(sel.termino.length > 34 ? sel.termino.slice(0, 32) + '…' : sel.termino)}»`;
    b.style.left = Math.min(innerWidth - 120, Math.max(120, sel.rect.left + sel.rect.width / 2)) + 'px';
    b.style.top = Math.min(innerHeight - 50, sel.rect.bottom) + 'px';
    b.hidden = false;
    b.onclick = () => { b.hidden = true; window.getSelection().removeAllRanges(); consAbrir(sel.termino.length > 60 ? sel.termino : `¿Qué significa «${sel.termino}»?`, sel.contexto); };
  }, 10);
});
document.addEventListener('mousedown', e => { if (!e.target.closest('#consSel')) $('#consSel').hidden = true; });
document.addEventListener('scroll', () => { $('#consSel').hidden = true; }, true);
hidratar($('#consultor'));

// El Consejo — Asistente: asesor interno, fuera del hemiciclo. Explica cómo funciona El Consejo, recomienda
// ambiente, paneles y expertos, ordena el planteamiento antes de consultar y aclara conceptos.
const CONS_CLAVE = 'consultor.historial';
let consHist = JSON.parse(localStorage[CONS_CLAVE] || '[]'), consCtx = '', consOcupado = false, consModo = null;
const consGuardar = () => { localStorage[CONS_CLAVE] = JSON.stringify(consHist.slice(-40)); };
const sinAcentos = t => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();

function consAbrir(termino, contexto, modo) {
  const dlg = $('#consultor');
  const sobreModal = !!document.querySelector('dialog[open]:not(#consultor):modal');
  if (dlg.open && dlg.matches(':modal') !== sobreModal) dlg.close();   // encima de un acta o una votación: modal
  if (!dlg.open) sobreModal ? dlg.showModal() : dlg.show();
  $('#lateral').hidden = true;
  consCtx = contexto || '';
  pintarConsCtx();
  consPintar();
  if (termino) { $('#consPregunta').value = termino; consModo = modo || null; consPreguntar(); }
  else $('#consPregunta').focus();
}
function pintarConsCtx() {
  const c = $('#consCtx');
  c.hidden = !consCtx;
  c.innerHTML = consCtx ? `<span>«${esc(consCtx)}»</span><button type="button" aria-label="Quitar el pasaje">${ico('x')}</button>` : '';
  if (consCtx) c.querySelector('button').onclick = () => { consCtx = ''; pintarConsCtx(); };
}
// separa la respuesta visible del bloque ```json con la recomendación aplicable
function partirRespuesta(t) {
  const m = (t || '').match(/```json\s*([\s\S]*?)(```|$)/);
  if (!m) return { texto: t, rec: null };
  let rec = null;
  try { rec = JSON.parse(m[1]); } catch { /* aún llegando o mal formado */ }
  return { texto: t.slice(0, m.index).trim(), rec };
}
function panelPorNombre(n) { const k = sinAcentos(n); return paneles.find(p => sinAcentos(p.nombre) === k) || paneles.find(p => k && sinAcentos(p.nombre).includes(k)); }
function expertoPorNombre(n) {
  const k = sinAcentos(n);
  for (const p of paneles) { if (p.tipo === 'asamblea') continue; const a = p.agentes.find(x => sinAcentos(x.nombre) === k || (k && sinAcentos(x.nombre).includes(k))); if (a) return { p, a }; }
  return null;
}
function destinoRec(rec) {
  const pans = (rec.paneles || []).map(panelPorNombre).filter(Boolean);
  const exp = rec.experto ? expertoPorNombre(rec.experto) : null;
  const amb = rec.ambiente === 'individual' && exp ? 'despacho' : rec.ambiente === 'asamblea' && pans.length > 1 ? 'asamblea' : pans[0] ? 'panel' : null;
  const nombre = amb === 'despacho' ? `el despacho de ${exp.a.nombre}` : amb === 'asamblea' ? `la Asamblea (${pans.length} comités)` : amb === 'panel' ? pans[0].nombre : '';
  return { pans, exp, amb, nombre };
}
function htmlRec(rec, i) {
  if (!rec || document.body.classList.contains('observador')) return '';
  const { amb, nombre } = destinoRec(rec);
  if (!amb) return '';
  const orden = (rec.orden_dia || []).filter(Boolean);
  return `<div class="rec"><div class="sobre">Recomendación · ${esc(nombre)}</div>
    ${rec.planteamiento ? `<div class="sintesis" data-sint="${i}"><b>${esc(rec.asunto || 'Síntesis del caso')}</b><p>${esc(rec.planteamiento)}</p>
      ${orden.length > 1 ? `<small>Orden del día: ${orden.map((x, k) => `${k + 1}. ${esc(x)}`).join(' · ')}</small>` : ''}</div>` : ''}
    <div class="acciones-rec">
      ${rec.planteamiento ? `<button type="button" class="dorado peq" data-rec="${i}" data-acc="iniciar">${ico('mazo')}<span class="etq">Iniciar sesión con esta síntesis</span></button>
        <button type="button" class="enlace peq" data-rec="${i}" data-acc="editar">Editar antes</button>` : ''}
      <button type="button" class="contorno peq" data-rec="${i}" data-acc="ir">${ico('flecha')}<span>Solo ir</span></button>
    </div></div>`;
}
// iniciar: abre el ambiente, abre la sesión con asunto y orden del día y plantea el caso. editar: deja el texto listo.
async function aplicarRec(rec, acc) {
  const { pans, exp, amb } = destinoRec(rec);
  const orden = (rec.orden_dia || []).filter(Boolean);
  const asunto = (rec.asunto || rec.planteamiento || '').slice(0, 200);
  const caso = rec.planteamiento || '';
  $('#consultor').close();
  if (amb === 'asamblea') {
    await irA('asamblea');
    if (sesion) {
      if (acc !== 'ir' && caso && await confirmar(`La Asamblea ya está reunida (sesión nº ${sesion.numero}). ¿Plantear el caso en ella?`, 'Plantear')) plantear(caso, acc);
      return;
    }
    if (acc === 'ir') return;
    await abrirConvocatoria();
    $('#formAsamblea').asunto.value = asunto;
    $('#formAsamblea').orden_dia.value = orden.join('\n');
    asaSel = {}; for (const p of pans) asaSel[p.id] = new Set([p.agentes[0].id]);
    pintarComites();
    casoPendiente = { texto: caso, enviar: acc === 'iniciar' };   // al convocar, se plantea
    avisar('Revise los comités y delegados y pulse «Convocar la Asamblea»: el caso se planteará a continuación.');
    return;
  }
  if (amb === 'despacho') await irA('individual', { panel: exp.p.id, agente: exp.a.id });
  else await irA('panel', { panel: pans[0].id });
  if (acc === 'ir' || !caso) return;
  if (sesion && sesion.consultas) {
    if (!await confirmar(`Este consejo tiene abierta la sesión nº ${sesion.numero} («${sesion.asunto}»). ¿Plantear el caso en ella? Si prefiere una sesión nueva, cierre antes la actual.`, 'Plantear en ella')) return;
  } else if (!sesion) {
    try {
      await api(`/api/paneles/${panel.id}/sesiones`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asunto, orden_dia: orden, modo_debate: 'orden', individual: enDespacho() ? expertoInd.agente : undefined }) });
      await refrescarSesion(); avisar(`Sesión nº ${sesion.numero} abierta: «${asunto}».`);
    } catch (e) { return avisar(e.message, true); }
  }
  plantear(caso, acc);
}
let casoPendiente = null;
function plantear(texto, acc) {
  $('#texto').value = texto; autoAlto();
  if (acc === 'iniciar') $('#chat').requestSubmit(); else $('#texto').focus();
}
function consPintar() {
  const box = $('#consHist');
  if (!consHist.length) {
    box.innerHTML = `<div class="cons-vacio">${ORNAMENTO}<p>¿En qué puedo ayudarle?</p>
      <small>Le explico cómo funciona El Consejo, le recomiendo el ambiente, el panel o el experto adecuados para su caso,
      ordeno su planteamiento antes de presentarlo y aclaro palabras o conceptos. No opino sobre el fondo del asunto.
      También puede <b>seleccionar un término</b> en cualquier respuesta o acta y pulsar «Preguntar al Asistente».</small></div>`;
    return;
  }
  box.innerHTML = consHist.map((h, i) => { const { texto, rec } = partirRespuesta(h.r);
    return `<div class="cons-item" data-i="${i}">
      <div class="pq"><b>${esc(h.etiqueta || h.p)}</b>${h.ctx ? `<em>«${esc(h.ctx.slice(0, 160))}${h.ctx.length > 160 ? '…' : ''}»</em>` : ''}</div>
      <div class="rs ${h.error ? 'error' : ''}"><div class="cuerpo">${texto ? md(texto) : h.error ? esc(h.error) : '<div class="pensando-txt">Pensando<span class="puntos"><i></i><i></i><i></i></span></div>'}</div></div>
      ${htmlRec(rec, i)}
      <div class="hora">${h.panel ? esc(h.panel) + ' · ' : ''}${new Date(h.ts).toLocaleString('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div></div>`; }).join('');
  box.querySelectorAll('[data-rec]').forEach(b => b.onclick = () => { const r = partirRespuesta(consHist[+b.dataset.rec].r).rec; if (r) aplicarRec(r, b.dataset.acc); });
  box.querySelectorAll('.sintesis p').forEach(p => p.title = 'Síntesis preparada por el Asistente');
  box.scrollTop = box.scrollHeight;
}
async function consPreguntar(etiqueta) {
  const p = $('#consPregunta').value.trim();
  if (!p || consOcupado) return;
  const modo = consModo; consModo = null;
  consOcupado = true; $('#consEnviar').disabled = true; $('#consPregunta').value = '';
  const item = { p, etiqueta, ctx: consCtx, r: '', ts: Date.now(), panel: panel && ambiente !== 'inicio' ? panel.nombre : '' };
  consHist.push(item); consCtx = ''; pintarConsCtx(); consPintar();
  const caja = () => $(`#consHist [data-i="${consHist.indexOf(item)}"] .cuerpo`);
  let raf = 0;
  try {
    const fin = await flujo('/api/asistente', x => {
      item.r += x;
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; const c = caja(); if (c) { c.innerHTML = md(partirRespuesta(item.r).texto); $('#consHist').scrollTop = $('#consHist').scrollHeight; } });
    }, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pregunta: p, contexto: item.ctx, modo,
         historial: consHist.slice(0, -1).filter(h => h.r && !h.error).slice(-3).map(h => ({ p: h.p, r: h.r })),
         panel_id: panel && ambiente !== 'inicio' ? panel.id : null,
         ambiente: { inicio: 'menú principal', panel: 'consulta de panel', asamblea: 'Asamblea General', individual: 'consulta individual' }[ambiente] }) });
    item.r = fin.texto || item.r;
    if (fin.error) item.error = fin.error;
  } catch (e) { item.error = e.message; }
  consGuardar(); consPintar(); pedirConsumo();
  consOcupado = false; $('#consEnviar').disabled = false; $('#consPregunta').focus();
}
// acciones rápidas
$('#consRapidas').querySelectorAll('[data-r]').forEach(b => b.onclick = () => {
  if (b.dataset.r === 'como') { $('#consPregunta').value = '¿Cómo funciona El Consejo y qué ambiente me conviene usar en cada caso?'; consPreguntar(); }
  else if (b.dataset.r === 'recomendar') { $('#consPregunta').value = 'Necesito consultar sobre: '; $('#consPregunta').focus(); }
  else {   // ordenar: lo escrito en la barra de consulta o en el campo del asistente
    const texto = $('#texto').value.trim() || $('#consPregunta').value.trim();
    if (!texto) { $('#consPregunta').placeholder = 'Escriba aquí su planteamiento y pulse «Ordenar mi planteamiento»'; $('#consPregunta').focus(); return; }
    $('#consPregunta').value = texto; consModo = 'ordenar'; consPreguntar(`Ordenar: ${texto.slice(0, 90)}${texto.length > 90 ? '…' : ''}`);
  }
});
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
    b.innerHTML = `${ico('asistente')} Preguntar al Asistente: «${esc(sel.termino.length > 30 ? sel.termino.slice(0, 28) + '…' : sel.termino)}»`;
    b.style.left = Math.min(innerWidth - 120, Math.max(120, sel.rect.left + sel.rect.width / 2)) + 'px';
    b.style.top = Math.min(innerHeight - 50, sel.rect.bottom) + 'px';
    b.hidden = false;
    b.onclick = () => { b.hidden = true; window.getSelection().removeAllRanges(); consAbrir(sel.termino.length > 60 ? sel.termino : `¿Qué significa «${sel.termino}»?`, sel.contexto, 'termino'); };
  }, 10);
});
document.addEventListener('mousedown', e => { if (!e.target.closest('#consSel')) $('#consSel').hidden = true; });
document.addEventListener('scroll', () => { $('#consSel').hidden = true; }, true);
hidratar($('#consultor'));

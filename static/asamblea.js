// El Consejo — Asamblea General: convocatoria de comités, lista de oradores y derecho de palabra.
const MAX_DELEGADOS = 16;
const oradores = [];   // {id, tipo: 'alusion'|'pide'|'orden', por, motivo} — reflejo de la lista del servidor
const esAsamblea = () => panel && panel.tipo === 'asamblea';
const corto = c => (c || '').replace(/^(Panel|Consejo)\s+(de\s+|del\s+)?/i, '');

// ---- lista de oradores (se guarda en el servidor: sobrevive a una recarga) ----
function fijarOradores(lista) { oradores.splice(0, oradores.length, ...(lista || [])); }
async function guardarOradores() {
  if (!sesion) return;
  try { fijarOradores(await api(`/api/sesiones/${sesion.id}/oradores`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ oradores }) })); }
  catch (e) { avisar(e.message, true); }
}
function anotarAlusiones(quien, ids) {   // respaldo si el servidor no devolvió la lista
  if (!esAsamblea()) return;
  for (const id of ids) if (id !== quien && !oradores.some(o => o.id === id)) oradores.push({ id, tipo: 'alusion', por: quien });
  pintarOradores();
}
const ETQ_ORADOR = { alusion: o => `por alusiones de ${esc((agenteDe(o.por) || {}).nombre || 'un delegado')}`,
  pide: o => `pide la palabra${o.motivo ? ': ' + esc(o.motivo) : ''}`, orden: o => `cuestión de orden${o.motivo ? ': ' + esc(o.motivo) : ''}` };
function pintarOradores() {
  const box = $('#oradores');
  const visible = esAsamblea() && sesion && qActual && !document.body.classList.contains('observador');
  box.hidden = !visible;
  if (!visible) return;
  const chips = oradores.map((o, i) => { const a = agenteDe(o.id); if (!a) return '';
    return `<span class="orador ${o.tipo}" style="--c:${a.color}"><span class="mini">${esc(monograma(a))}</span>
      <span class="q"><b>${esc(a.nombre)}</b><em>${(ETQ_ORADOR[o.tipo] || ETQ_ORADOR.pide)(o)}</em></span>
      <button type="button" class="contorno peq" data-dar="${i}">${ico('mazo')}<span>Conceder</span></button>
      <button type="button" class="icono" data-quitar="${i}" aria-label="Retirar de la lista">${ico('x')}</button></span>`; }).join('');
  box.innerHTML = `<div class="cab-or"><span class="s-num">Lista de oradores</span>${oradores.length ? '' : '<span class="ayuda">Nadie ha pedido la palabra</span>'}
      <span class="grow"></span>
      <button type="button" class="enlace peq" id="orSolicitar" title="Cada delegado decide si quiere intervenir o plantear una cuestión de orden">${ico('persona')}<span>Solicitudes</span></button>
      <div class="desplegable"><button type="button" class="enlace peq" id="orMociones" title="Mociones de procedimiento que votan los delegados">${ico('balanza')}<span>Mociones</span></button>
        <div class="menu-mini" id="menuMociones" hidden>
          <button type="button" data-m="cierre">Cierre del debate <small>y pasar a votar el acuerdo</small></button>
          ${sesion.orden_dia.length > 1 && sesion.punto < sesion.orden_dia.length - 1 ? '<button type="button" data-m="siguiente">Pasar al siguiente punto</button>' : ''}
          <button type="button" data-m="limite" data-n="80">Limitar el tiempo de palabra a 80 palabras</button>
          <button type="button" data-m="limite" data-n="120">Limitar el tiempo de palabra a 120 palabras</button>
          <button type="button" data-m="cuarto">Cuarto intermedio</button>
        </div></div>
      <select id="orDar" title="Conceder la palabra a un delegado"><option value="">Dar la palabra a…</option>
        ${panel.agentes.map(a => `<option value="${a.id}">${esc(a.nombre)} · ${esc(corto(a.comite))}</option>`).join('')}</select></div>
    ${chips ? `<div class="chips">${chips}</div>` : ''}`;
  box.querySelectorAll('[data-dar]').forEach(b => b.onclick = () => { const o = oradores[+b.dataset.dar]; concederPalabra(o.id, o.tipo === 'pide' ? 'palabra' : o.tipo, o.por); });
  box.querySelectorAll('[data-quitar]').forEach(b => b.onclick = () => { oradores.splice(+b.dataset.quitar, 1); pintarOradores(); guardarOradores(); });
  $('#orDar').onchange = e => { if (e.target.value) concederPalabra(e.target.value, 'palabra'); };
  $('#orSolicitar').onclick = abrirSolicitudes;
  $('#orMociones').onclick = e => { e.stopPropagation(); $('#menuMociones').hidden = !$('#menuMociones').hidden; };
  $('#menuMociones').querySelectorAll('[data-m]').forEach(b => b.onclick = () => { $('#menuMociones').hidden = true; mocion(b.dataset.m, b.dataset.n); });
}
document.addEventListener('click', e => { const m = $('#menuMociones'); if (m && !e.target.closest('.desplegable')) m.hidden = true; });
async function concederPalabra(id, modo = 'palabra', por = null) {
  if (!qActual || $('#enviar').disabled) return avisar(qActual ? 'Espere a que termine la intervención en curso.' : 'Plantee primero el asunto a la Asamblea.', true);
  if (sesion && sesion.receso) return avisar('La sesión está en cuarto intermedio.', true);
  const a = agenteDe(id); if (!a) return;
  const i = oradores.findIndex(o => o.id === id); if (i >= 0) oradores.splice(i, 1);
  const q = qActual, pid = panel.id, vigente = () => panel && panel.id === pid && qActual === q;
  ocupado(true, 'En uso de la palabra');
  progreso = { ronda: 0, hechos: 0, de: 1, turno: a.nombre,
    titulo: { alusion: 'Réplica por alusiones', orden: 'Cuestión de orden' }[modo] || 'Uso de la palabra' };
  estado[id] = 'pensando'; sel = id;
  pintarOradores(); pintarArco(); pintarMesa();
  await intervenir(q, id, { modo, por, vigente });
  progreso = null; pintarDescripcion(); ocupado(false); pintarOradores(); pintarMesa();
}
async function abrirSolicitudes() {
  if (!qActual || $('#enviar').disabled) return;
  const b = $('#orSolicitar'); b.disabled = true; b.querySelector('span').textContent = 'Consultando…';
  try {
    const ultimo = [...msgs].reverse().find(m => m.rol === 'agent' && !m.error);
    const r = await api(`/api/preguntas/${qActual}/solicitudes${ultimo ? `?excluir=${ultimo.agente_id}` : ''}`, { method: 'POST' });
    if (r.oradores) fijarOradores(r.oradores);
    const ordenes = r.piden.filter(p => p.tipo === 'orden').length, piden = r.piden.length - ordenes;
    avisar(!r.piden.length ? 'Ningún delegado pide la palabra: puede pasar a deliberar el acuerdo.'
      : [piden ? `${piden} delegado${piden > 1 ? 's piden' : ' pide'} la palabra` : '', ordenes ? `${ordenes} cuestión${ordenes > 1 ? 'es' : ''} de orden` : ''].filter(Boolean).join(' · ') + '.');
    pedirConsumo();
  } catch (e) { avisar(e.message, true); }
  pintarOradores();
}
async function mocion(tipo, n) {
  if (!sesion || $('#enviar').disabled) return;
  ocupado(true, 'Votando la moción');
  try {
    const r = await api(`/api/sesiones/${sesion.id}/mociones`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tipo, palabras: n ? +n : undefined }) });
    sesion = r.sesion; fijarOradores(sesion.oradores);
    avisar(`${r.mocion}: ${r.resultado.texto}.`, !r.resultado.aprobada);
    pedirConsumo(); pintarSesionBar(); pintarOradores();
    if (r.resultado.aprobada && tipo === 'siguiente') { qActual = null; estado = {}; sel = null; pintarArco(); pintarMesa(); }
    if (r.resultado.aprobada && tipo === 'cierre') { ocupado(false); abrirVotacion(); return; }
  } catch (e) { avisar(e.message, true); }
  ocupado(false);
}

// ---- convocatoria ----
let asaLimite = '120', asaModo = 'orden', asaSel = {};   // panel_id -> Set de delegados
async function abrirConvocatoria() {
  const f = $('#formAsamblea'); f.asunto.value = $('#texto').value.trim().slice(0, 200);
  asaSel = {};
  pintarSegmentos(); pintarComites();
  $('#asaAnexos').innerHTML = '<p class="ayuda">Cargando actas…</p>';
  $('#dlgAsamblea').showModal();
  const actas = await api('/api/sesiones?con_acta=1').catch(() => []);
  $('#asaAnexos').innerHTML = actas.map(a => `<label class="anexo"><input type="checkbox" value="${a.id}">
      <span><b>${esc(a.panel)} · sesión nº ${a.numero}</b><em>${esc(a.asunto)}</em><small>${fechaHora(a.cerrada)}${a.acuerdo ? ' · con acuerdo' : ''}</small></span></label>`).join('')
    || '<p class="ayuda">Aún no hay actas de cierre que anexar.</p>';
}
function pintarSegmentos() {
  $('#asaLimite').querySelectorAll('[data-l]').forEach(b => b.classList.toggle('act', b.dataset.l === asaLimite));
  $('#asaModo').querySelectorAll('[data-m]').forEach(b => b.classList.toggle('act', b.dataset.m === asaModo));
}
$('#asaLimite').querySelectorAll('[data-l]').forEach(b => b.onclick = () => { asaLimite = b.dataset.l; pintarSegmentos(); });
$('#asaModo').querySelectorAll('[data-m]').forEach(b => b.onclick = () => { asaModo = b.dataset.m; pintarSegmentos(); });
function pintarComites() {
  const total = Object.values(asaSel).reduce((n, s) => n + s.size, 0);
  $('#asaCuenta').textContent = `${total} de ${MAX_DELEGADOS}`;
  $('#asaCuenta').classList.toggle('mal', total > MAX_DELEGADOS);
  $('#asaComites').innerHTML = paneles.filter(p => p.tipo !== 'asamblea' && p.agentes.length).map(p => {
    const s = asaSel[p.id];
    return `<div class="comite ${s ? 'act' : ''}" data-p="${p.id}">
      <label class="c-cab"><input type="checkbox" ${s ? 'checked' : ''}><b>${esc(p.nombre)}</b><em>${p.agentes.length} expertos</em></label>
      ${s ? `<div class="c-del">${p.agentes.map((a, i) => `<button type="button" class="del ${s.has(a.id) ? 'act' : ''}" data-a="${a.id}" title="${esc(a.rol)}">
          ${esc(a.nombre)}${i === 0 ? ' <small>portavoz</small>' : ''}</button>`).join('')}
        <button type="button" class="enlace peq" data-todos>${s.size === p.agentes.length ? 'Solo portavoz' : 'Todo el comité'}</button></div>` : ''}
    </div>`; }).join('');
  $('#asaComites').querySelectorAll('.comite').forEach(el => {
    const p = paneles.find(x => x.id === el.dataset.p);
    el.querySelector('.c-cab input').onchange = e => { if (e.target.checked) asaSel[p.id] = new Set([p.agentes[0].id]); else delete asaSel[p.id]; pintarComites(); };
    el.querySelectorAll('[data-a]').forEach(b => b.onclick = () => { const s = asaSel[p.id]; s.has(b.dataset.a) ? s.delete(b.dataset.a) : s.add(b.dataset.a); if (!s.size) delete asaSel[p.id]; pintarComites(); });
    const t = el.querySelector('[data-todos]');
    if (t) t.onclick = () => { const s = asaSel[p.id]; asaSel[p.id] = s.size === p.agentes.length ? new Set([p.agentes[0].id]) : new Set(p.agentes.map(a => a.id)); pintarComites(); };
  });
}
$('#formAsamblea').onsubmit = async e => {
  e.preventDefault();
  const comites = Object.entries(asaSel).map(([panel_id, s]) => ({ panel_id, delegados: [...s] }));
  if (comites.length < 2) return avisar('Convoque al menos dos comités.', true);
  const total = comites.reduce((n, c) => n + c.delegados.length, 0);
  if (total > MAX_DELEGADOS) return avisar(`Como máximo ${MAX_DELEGADOS} delegados.`, true);
  try {
    await api('/api/asamblea/sesiones', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      asunto: e.target.asunto.value.trim(), limite_palabras: asaLimite ? +asaLimite : null, modo_debate: asaModo, comites,
      orden_dia: e.target.orden_dia.value.split('\n').map(l => l.replace(/^\s*\d+[.)]\s*/, '').trim()).filter(Boolean),
      anexos: [...$('#asaAnexos').querySelectorAll('input:checked')].map(i => +i.value) }) });
    $('#dlgAsamblea').close();
    const asam = paneles.find(p => p.tipo === 'asamblea');
    ultimoPanel = null; await cargar(asam.id);
    avisar(`Asamblea convocada: ${comites.length} comités, ${total} delegados.${typeof casoPendiente !== 'undefined' && casoPendiente ? '' : ' Plantee el asunto para abrir la ronda de posiciones.'}`);
    if (typeof casoPendiente !== 'undefined' && casoPendiente) {   // viene del Asistente: se plantea el caso sintetizado
      const c = casoPendiente; casoPendiente = null; plantear(c.texto, c.enviar ? 'iniciar' : 'editar');
    } else { $('#texto').value = e.target.asunto.value.trim(); autoAlto(); $('#texto').focus(); }
  } catch (err) { avisar(err.message, true); }
};

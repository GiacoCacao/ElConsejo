// El Consejo — sesiones: convocatoria, orden del debate, votación, acta de cierre y registro.
// Usa el estado y las utilidades de consejo.js (panel, sesion, msgs, api, esc, ico, monograma…).

const fechaHora = ts => ts ? new Date(ts * 1000).toLocaleString('es', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const agenteDe = id => panel && panel.agentes.find(a => a.id === id);
document.querySelectorAll('[data-cierra]').forEach(b => b.addEventListener('click', () => $('#' + b.dataset.cierra).close()));

async function refrescarSesion() {
  if (!panel) return;
  const est = await api(`/api/paneles/${panel.id}/sesion`).catch(() => null);
  if (!est) return;
  sesion = est.sesion; votaciones = est.votaciones;
  pintarSesionBar(); pintarArco(); pintarRegistro();
}

// ---- barra de sesión (sobre el atril) ----
function pintarSesionBar() {
  const b = $('#sesionBar');
  if (!panel) { b.innerHTML = ''; return; }
  if (!sesion) {
    b.className = 'sesionbar vacia';
    b.innerHTML = `<span class="s-vacia">Sin sesión abierta · al consultar se abrirá una</span><span class="grow"></span>
      <button type="button" class="contorno peq" id="sbIniciar">${ico('mazo')}<span>Iniciar sesión</span></button>`;
    $('#sbIniciar').onclick = () => abrirDlgSesion(null);
    return;
  }
  const n = sesion.anexos.length;
  b.className = 'sesionbar';
  b.innerHTML = `<span class="s-num">Sesión nº ${sesion.numero}</span>
    <span class="s-asunto" title="${esc(sesion.asunto)}">${esc(sesion.asunto)}</span>
    ${sesion.estado === 'votacion' ? '<em class="s-chip vivo">En votación</em>' : ''}
    ${sesion.acuerdo ? '<em class="s-chip ok" title="Hay un acuerdo aprobado en esta sesión">Acuerdo adoptado</em>' : ''}
    ${n ? `<em class="s-chip" title="${esc(sesion.anexos.map(a => `Acta nº ${a.numero} · ${a.panel}`).join('\n'))}">${n} acta${n > 1 ? 's' : ''} anexa${n > 1 ? 's' : ''}</em>` : ''}
    <span class="grow"></span>
    <button type="button" class="enlace peq" id="sbOrden" title="Asunto, orden del debate y actas anexas">${ico('indice')}<span>Orden</span></button>
    <button type="button" class="enlace peq" id="sbDeliberar" title="Llegar a un acuerdo por consenso o por mayoría simple">${ico('balanza')}<span>Deliberar acuerdo</span></button>
    <button type="button" class="contorno peq" id="sbCerrar" title="Levantar el acta y concluir el asunto">${ico('sello')}<span>Acta de cierre</span></button>`;
  $('#sbOrden').onclick = () => abrirDlgSesion(sesion);
  $('#sbDeliberar').onclick = abrirVotacion;
  $('#sbCerrar').onclick = cerrarSesion;
}

// ---- convocatoria: iniciar o editar sesión ----
let sesEdit = null, sesModo = 'orden', sesOrden = [];
async function abrirDlgSesion(s) {
  if (!panel) return;
  if (!panel.agentes.length) return avisar('Este panel no tiene expertos todavía.', true);
  sesEdit = s; const f = $('#formSesion');
  $('#sesSobre').textContent = s ? `Sesión nº ${s.numero} · en curso` : `Convocatoria · ${panel.nombre}`;
  $('#sesTitulo').textContent = s ? 'Orden de la sesión' : 'Iniciar sesión';
  $('#sesGuardar .etq').textContent = s ? 'Guardar' : 'Abrir sesión';
  f.asunto.value = s ? s.asunto : ($('#texto').value.trim().slice(0, 200) || '');
  sesModo = s ? s.modo_debate : 'orden';
  sesOrden = s ? [...s.orden] : panel.agentes.map(a => a.id);
  pintarModo(); pintarOrden();
  $('#sesAnexos').innerHTML = '<p class="ayuda">Cargando actas…</p>';
  $('#dlgSesion').showModal();
  const actas = await api('/api/sesiones?con_acta=1').catch(() => []);
  const marcadas = new Set((s ? s.anexos : []).map(a => a.id));
  $('#sesAnexos').innerHTML = actas.filter(a => !s || a.id !== s.id).map(a => `<label class="anexo">
      <input type="checkbox" value="${a.id}" ${marcadas.has(a.id) ? 'checked' : ''}>
      <span><b>${esc(a.panel)} · sesión nº ${a.numero}</b><em>${esc(a.asunto)}</em><small>${fechaHora(a.cerrada)}${a.acuerdo ? ' · con acuerdo' : ''}</small></span></label>`).join('')
    || '<p class="ayuda">Aún no hay actas de cierre. Cuando cierre una sesión, podrá anexar su acta aquí.</p>';
}
function pintarModo() {
  $('#sesModo').querySelectorAll('[data-m]').forEach(b => b.classList.toggle('act', b.dataset.m === sesModo));
  $('#sesModoAyuda').textContent = sesModo === 'orden'
    ? 'Cada experto interviene en su turno y escucha a quienes hablaron antes: un debate de verdad, algo más lento.'
    : 'Todos responden a la vez sin oírse; las réplicas (si las activa) se hacen después. Más rápido.';
}
$('#sesModo').querySelectorAll('[data-m]').forEach(b => b.onclick = () => { sesModo = b.dataset.m; pintarModo(); });
function pintarOrden() {
  const ol = $('#sesOrden'); ol.innerHTML = '';
  sesOrden.forEach((id, i) => {
    const a = agenteDe(id); if (!a) return;
    const li = document.createElement('li'); li.draggable = true; li.dataset.id = id;
    li.innerHTML = `<span class="n">${i + 1}</span><span class="mini" style="--c:${a.color}">${esc(monograma(a))}</span>
      <span class="q"><b>${esc(a.nombre)}</b><em>${esc(a.rol)}</em></span>
      <button type="button" class="icono" data-d="-1" aria-label="Subir" ${i ? '' : 'disabled'}>${ico('arriba')}</button>
      <button type="button" class="icono" data-d="1" aria-label="Bajar" ${i < sesOrden.length - 1 ? '' : 'disabled'}>${ico('abajo')}</button>`;
    li.querySelectorAll('[data-d]').forEach(b => b.onclick = () => mover(i, i + +b.dataset.d));
    li.ondragstart = e => { e.dataTransfer.setData('text/plain', i); li.classList.add('arrastra'); };
    li.ondragend = () => li.classList.remove('arrastra');
    li.ondragover = e => e.preventDefault();
    li.ondrop = e => { e.preventDefault(); mover(+e.dataTransfer.getData('text/plain'), i); };
    ol.append(li);
  });
  function mover(de, a) {
    if (a < 0 || a >= sesOrden.length || de === a) return;
    const [x] = sesOrden.splice(de, 1); sesOrden.splice(a, 0, x); pintarOrden();
  }
}
$('#sesHemiciclo').onclick = () => { sesOrden = panel.agentes.map(a => a.id); pintarOrden(); };
$('#sesAzar').onclick = () => { for (let i = sesOrden.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [sesOrden[i], sesOrden[j]] = [sesOrden[j], sesOrden[i]]; } pintarOrden(); };
$('#formSesion').onsubmit = async e => {
  e.preventDefault();
  const cuerpo = { asunto: e.target.asunto.value.trim(), modo_debate: sesModo, orden: sesOrden,
    anexos: [...$('#sesAnexos').querySelectorAll('input:checked')].map(i => +i.value) };
  const h = { 'Content-Type': 'application/json' };
  try {
    if (sesEdit) await api(`/api/sesiones/${sesEdit.id}`, { method: 'PUT', headers: h, body: JSON.stringify(cuerpo) });
    else await api(`/api/paneles/${panel.id}/sesiones`, { method: 'POST', headers: h, body: JSON.stringify(cuerpo) });
    $('#dlgSesion').close();
    if (sesEdit) { await refrescarSesion(); avisar('Orden de la sesión actualizado.'); }
    else { await cargar(panel.id); avisar('Sesión abierta. El Consejo está reunido.'); $('#texto').focus(); }
  } catch (err) { avisar(err.message, true); }
};

// ---- votación (pantalla completa) ----
let vTipo = 'consenso', vActual = null, vAbortar = false;
const ETQ = { favor: 'A favor', contra: 'En contra', abstencion: 'Abstención' };
function abrirVotacion() {
  if (!sesion) return avisar('No hay sesión abierta.', true);
  if (!msgs.some(m => m.rol === 'agent' && !m.error)) return avisar('Antes de deliberar un acuerdo, plantee una consulta y escuche a los expertos.', true);
  vAbortar = false;
  $('#votacion').showModal();
  const abierta = votaciones.find(v => v.estado === 'abierta');
  abierta ? vVotar(abierta) : vElegir();
}
$('#vCerrar').onclick = () => { vAbortar = true; $('#votacion').close(); };
$('#votacion').addEventListener('cancel', () => { vAbortar = true; });
$('#votacion').addEventListener('close', () => { refrescarSesion(); pedirConsumo(); });
const vCab = (sobre, titulo) => { $('#vSobre').textContent = sobre; $('#vTitulo').textContent = titulo; };

function vElegir() {
  vCab(`Sesión nº ${sesion.numero} · ${sesion.asunto}`, 'Deliberar un acuerdo');
  $('#vCuerpo').innerHTML = `<p class="v-intro">Elija cómo debe concluir el Consejo. La Secretaría preparará el texto a partir del debate; podrá revisarlo antes de someterlo a votación.</p>
    <div class="v-modos">
      <button type="button" class="v-modo" data-t="consenso">${ico('sello')}<b>Acuerdo unificado</b>
        <span>La Secretaría redacta una propuesta que integra las posiciones. Se aprueba si ningún experto vota en contra; si no, se revisa con sus objeciones.</span><em>Consenso</em></button>
      <button type="button" class="v-modo" data-t="mayoria">${ico('balanza')}<b>Mayoría simple</b>
        <span>La Secretaría identifica las alternativas surgidas en el debate. Gana la más votada; un empate lo resuelve su voto de calidad.</span><em>Votación</em></button>
    </div>`;
  $('#vCuerpo').querySelectorAll('[data-t]').forEach(b => b.onclick = () => vPropuesta(b.dataset.t));
}

async function vPropuesta(tipo, revisar) {
  vTipo = tipo;
  vCab(tipo === 'consenso' ? 'Acuerdo unificado' : 'Mayoría simple', revisar ? 'Revisión de la propuesta' : 'Propuesta de la Secretaría');
  $('#vCuerpo').innerHTML = `<div class="v-espera"><span class="puntos"><i></i><i></i><i></i></span>La Secretaría ${revisar ? 'revisa la propuesta con las objeciones' : 'estudia el debate y redacta'}…</div>`;
  let r;
  try { r = await api(`/api/sesiones/${sesion.id}/propuesta`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tipo, revisar }) }); }
  catch (e) { $('#vCuerpo').innerHTML = `<p class="v-intro error">${esc(e.message)}</p><div class="botones"><button type="button" class="enlace" id="vVolver">Volver</button></div>`; $('#vVolver').onclick = vElegir; return; }
  if (r.aviso) avisar(r.aviso);
  vTipo = r.tipo;
  const alts = r.alternativas || [];
  $('#vCuerpo').innerHTML = `<p class="v-intro">${vTipo === 'consenso' ? 'Revise y, si lo desea, corrija la propuesta antes de abrir la votación.' : 'Revise las alternativas: puede corregirlas, añadir o quitar (entre 2 y 5).'}</p>
    ${vTipo === 'consenso' ? `<textarea id="vTexto" class="v-texto" rows="7">${esc(r.propuesta)}</textarea>`
      : `<div id="vAlts" class="v-alts"></div><button type="button" class="enlace" id="vMas">${ico('mas')}<span>Añadir alternativa</span></button>`}
    <div class="botones"><button type="button" class="enlace" id="vVolver">Volver</button><span class="grow"></span>
      <button type="button" class="dorado" id="vAbrir"><span class="etq">Someter a votación</span></button></div>`;
  if (vTipo === 'mayoria') {
    const pintaAlts = lista => {
      $('#vAlts').innerHTML = lista.map((a, i) => `<div class="v-alt"><span class="letra">${String.fromCharCode(65 + i)}</span>
        <textarea rows="2">${esc(a)}</textarea><button type="button" class="icono" data-q="${i}" aria-label="Quitar">${ico('x')}</button></div>`).join('');
      $('#vAlts').querySelectorAll('[data-q]').forEach(b => b.onclick = () => { const l = leerAlts(); l.splice(+b.dataset.q, 1); pintaAlts(l); });
    };
    const leerAlts = () => [...$('#vAlts').querySelectorAll('textarea')].map(t => t.value);
    pintaAlts(alts.map(a => a.texto));
    $('#vMas').onclick = () => { const l = leerAlts(); if (l.length < 5) pintaAlts([...l, '']); };
  }
  $('#vVolver').onclick = vElegir;
  $('#vAbrir').onclick = async () => {
    const cuerpo = { tipo: vTipo };
    if (vTipo === 'consenso') cuerpo.propuesta = $('#vTexto').value.trim();
    else cuerpo.alternativas = [...$('#vAlts').querySelectorAll('textarea')].map(t => ({ texto: t.value.trim() })).filter(a => a.texto);
    if (vTipo === 'mayoria' && cuerpo.alternativas.length < 2) return avisar('Hacen falta al menos dos alternativas.', true);
    try {
      const v = await api(`/api/sesiones/${sesion.id}/votaciones`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
      sesion.estado = 'votacion'; vVotar(v);
    } catch (e) { avisar(e.message, true); }
  };
}

function vTablero(v, actual) {
  const votos = Object.fromEntries(v.votos.map(x => [x.agente_id, x]));
  const orden = sesion.orden.filter(id => agenteDe(id));
  const emitidos = v.votos.length;
  let objeto, marcador;
  if (v.alternativas.length) {
    const cuenta = Object.fromEntries(v.alternativas.map(a => [a.letra, 0]));
    v.votos.forEach(x => { if (x.opcion in cuenta) cuenta[x.opcion]++; });
    const maxN = Math.max(1, orden.length);
    objeto = `<div class="sobre">Alternativas sometidas a votación</div><div class="v-opciones">${v.alternativas.map(a => `
      <div class="v-op"><span class="letra">${a.letra}</span><span class="t">${esc(a.texto)}</span>
      <span class="barra"><i style="width:${100 * cuenta[a.letra] / maxN}%"></i></span><b>${cuenta[a.letra]}</b></div>`).join('')}</div>`;
    marcador = '';
  } else {
    const c = { favor: 0, contra: 0, abstencion: 0 }; v.votos.forEach(x => c[x.opcion]++);
    objeto = `<div class="sobre">Propuesta de acuerdo</div><blockquote class="v-propuesta">${esc(v.propuesta)}</blockquote>`;
    marcador = `<div class="v-marcador"><div class="favor"><b>${c.favor}</b>A favor</div><div class="contra"><b>${c.contra}</b>En contra</div><div class="abst"><b>${c.abstencion}</b>Abstención</div></div>`;
  }
  const escanos = orden.map((id, i) => {
    const a = agenteDe(id), x = votos[id];
    const cls = x ? (x.opcion in ETQ ? x.opcion : 'alt') : id === actual ? 'votando' : '';
    const etq = x ? (ETQ[x.opcion] || `Alternativa ${x.opcion}`) : id === actual ? 'Votando…' : 'Pendiente';
    return `<div class="escano ${cls}" style="--c:${a.color}"><span class="n">${i + 1}</span><div class="mini">${esc(monograma(a))}</div>
      <div class="nm">${esc(a.nombre)}</div><div class="vt">${etq}</div></div>`;
  }).join('');
  const motivos = v.votos.map(x => { const a = agenteDe(x.agente_id) || { nombre: 'Experto' };
    return `<div class="motivo"><b>${esc(a.nombre)}</b><em class="${x.opcion in ETQ ? x.opcion : 'alt'}">${ETQ[x.opcion] || 'Alternativa ' + x.opcion}</em><p>${esc(x.motivo)}</p></div>`; }).join('');
  return `<div class="v-tablero">${objeto}<div class="v-escanos">${escanos}</div>${marcador}
    <div class="v-prog">${emitidos} de ${orden.length} votos emitidos</div></div>
    ${motivos ? `<div class="v-motivos"><div class="sobre">Explicación de voto</div>${motivos}</div>` : ''}`;
}

async function vVotar(v) {
  vActual = v;
  vCab(`Votación ${v.intento} · ${v.alternativas.length ? 'mayoría simple' : v.tipo === 'consenso' ? 'acuerdo unificado' : 'mayoría simple'}`, 'Votación en curso');
  const pinta = actual => { $('#vCuerpo').innerHTML = vTablero(v, actual); };
  pinta(null);
  const yaVotaron = new Set(v.votos.map(x => x.agente_id));
  for (const id of sesion.orden.filter(id => agenteDe(id) && !yaVotaron.has(id))) {
    if (vAbortar || !$('#votacion').open) return;
    pinta(id);
    try {
      const x = await api(`/api/votaciones/${v.id}/votos/${id}`, { method: 'POST' });
      v.votos = v.votos.filter(y => y.agente_id !== id).concat([x]);
    } catch (e) { avisar(e.message, true); return; }
    pinta(null);
  }
  if (vAbortar) return;
  await vCerrarVotacion(v);
}

async function vCerrarVotacion(v, calidad) {
  try {
    const r = await api(`/api/votaciones/${v.id}/cerrar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ calidad }) });
    vResultado(r);
  } catch (e) { avisar(e.message, true); }
}

function vResultado(v) {
  const r = v.resultado;
  vCab(`Votación ${v.intento}`, r.aprobado ? 'Acuerdo adoptado' : r.estado === 'empate' ? 'Empate' : 'Sin acuerdo');
  const etqEmp = k => k === 'favor' ? 'A favor' : k === 'contra' ? 'En contra' : `Alternativa ${k}`;
  $('#vCuerpo').innerHTML = `<div class="v-resultado ${r.aprobado ? 'ok' : r.estado === 'empate' ? 'empate' : 'ko'}">
      <div class="sobre">Resultado</div><h3>${esc(r.texto)}</h3>
      ${r.acuerdo ? `<blockquote class="v-propuesta">${esc(r.acuerdo)}</blockquote>` : ''}
      ${r.estado === 'empate' ? `<p>Como presidencia, puede deshacer el empate con su voto de calidad:</p>
        <div class="v-calidad">${r.empatadas.map(k => `<button type="button" class="contorno" data-k="${k}">${esc(etqEmp(k))}</button>`).join('')}</div>` : ''}
    </div>
    <div class="botones arriba">
      ${r.estado === 'sin_consenso' ? `<button type="button" class="contorno" id="vRevisar">${ico('repetir')}<span>Revisar con las objeciones</span></button>
        <button type="button" class="enlace" id="vMayoria">Pasar a mayoría simple</button>` : ''}
      ${r.estado === 'rechazado' || r.estado === 'sin_votos' ? `<button type="button" class="contorno" id="vOtra">Nueva propuesta</button>` : ''}
      <span class="grow"></span>
      <button type="button" class="enlace" id="vSala">Volver a la sala</button>
      ${r.estado !== 'empate' ? `<button type="button" class="dorado" id="vActa"><span class="etq">Levantar acta de cierre</span></button>` : ''}
    </div>${vTablero(v, null)}`;
  $('#vCuerpo').querySelectorAll('[data-k]').forEach(b => b.onclick = () => vCerrarVotacion(v, b.dataset.k));
  const on = (id, fn) => { const el = $('#' + id); if (el) el.onclick = fn; };
  on('vRevisar', () => vPropuesta('consenso', v.id));
  on('vMayoria', () => vPropuesta('mayoria'));
  on('vOtra', vElegir);
  on('vSala', () => $('#votacion').close());
  on('vActa', () => { $('#votacion').close(); cerrarSesion(); });
}

// ---- acta de cierre ----
function mdDoc(t) {   // markdown del acta: títulos, citas, listas, negrita y cursiva (sobre texto escapado)
  const en = x => x.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
  let h = '', lista = null;
  const cierra = () => { if (lista) { h += `</${lista}>`; lista = null; } };
  for (const l of esc(t).split('\n')) {
    let m;
    if ((m = l.match(/^(#{1,3})\s+(.*)/))) { cierra(); h += `<h${m[1].length + 1}>${en(m[2])}</h${m[1].length + 1}>`; continue; }
    if ((m = l.match(/^&gt;\s?(.*)/))) { cierra(); h += `<blockquote>${en(m[1])}</blockquote>`; continue; }
    if ((m = l.match(/^\s*[-*]\s+(.*)/))) { if (lista !== 'ul') { cierra(); h += '<ul>'; lista = 'ul'; } h += `<li>${en(m[1])}</li>`; continue; }
    if ((m = l.match(/^\s*\d+\.\s+(.*)/))) { if (lista !== 'ol') { cierra(); h += '<ol>'; lista = 'ol'; } h += `<li>${en(m[1])}</li>`; continue; }
    cierra(); if (l.trim()) h += `<p>${en(l)}</p>`;
  }
  cierra(); return h;
}
let actaSesion = null;
async function verActa(sid) {
  $('#dlgActa').showModal();
  $('#actaDoc').innerHTML = '<div class="v-espera"><span class="puntos"><i></i><i></i><i></i></span>Cargando el acta…</div>';
  const r = await api(`/api/sesiones/${sid}`);
  mostrarActa(r.sesion, r.acta);
}
function mostrarActa(s, acta) {
  actaSesion = s;
  $('#actaSobre').textContent = `${s.panel} · sesión nº ${s.numero}`;
  $('#actaTitulo').textContent = 'Acta de cierre';
  $('#actaDoc').innerHTML = acta ? mdDoc(acta) : '<p class="ayuda">Esta sesión no tiene acta de cierre.</p>';
  $('#actaBar').hidden = !acta;
  $('#actaDescargar').href = `/api/sesiones/${s.id}/acta.md`;
  $('#actaDestino').innerHTML = paneles.map(p => `<option value="${p.id}" ${p.id === s.panel_id ? 'disabled' : ''}>${esc(p.nombre)}</option>`).join('');
  const primero = paneles.find(p => p.id !== s.panel_id); if (primero) $('#actaDestino').value = primero.id;
}
async function cerrarSesion() {
  if (!sesion) return;
  const pend = votaciones.some(v => v.estado === 'abierta');
  if (!await confirmar(`¿Levantar el acta y cerrar la sesión nº ${sesion.numero}? La Secretaría redactará el acta con lo debatido${sesion.acuerdo ? ' y el acuerdo adoptado' : ''}${pend ? '; la votación pendiente quedará anulada' : ''}.`, 'Levantar acta')) return;
  $('#dlgActa').showModal(); $('#actaBar').hidden = true;
  $('#actaSobre').textContent = `${panel.nombre} · sesión nº ${sesion.numero}`; $('#actaTitulo').textContent = 'Acta de cierre';
  $('#actaDoc').innerHTML = '<div class="v-espera"><span class="puntos"><i></i><i></i><i></i></span>La Secretaría está redactando el acta…</div>';
  try {
    const r = await api(`/api/sesiones/${sesion.id}/cerrar`, { method: 'POST' });
    mostrarActa(r.sesion, r.acta);
    avisar(`Sesión nº ${r.sesion.numero} cerrada. El acta queda en el registro.`);
    await cargar(panel.id); pedirConsumo();
  } catch (e) { $('#dlgActa').close(); avisar(e.message, true); }
}
$('#actaImprimir').onclick = () => {
  const w = window.open('', '_blank'); if (!w) return avisar('Permita las ventanas emergentes para imprimir.', true);
  w.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Acta · ${esc(actaSesion.panel)} · sesión ${actaSesion.numero}</title>
    <style>@font-face{font-family:C;src:url(${location.origin}/static/fuentes/cormorant.woff2)}@font-face{font-family:I;src:url(${location.origin}/static/fuentes/inter.woff2)}
    body{font:11pt/1.6 I,system-ui,sans-serif;color:#1d1a14;max-width:720px;margin:40px auto;padding:0 24px}
    h2{font:500 26pt/1.1 C,serif;margin:0 0 6px;text-align:center}h3{font:500 15pt C,serif;margin:22px 0 6px;border-bottom:1px solid #b89a5c;padding-bottom:3px}
    h4{font:500 12pt C,serif;margin:14px 0 4px}blockquote{margin:8px 0;padding:8px 14px;border-left:2px solid #b89a5c;background:#f6f1e6;font:italic 12pt C,serif}
    h2+p{text-align:center;color:#6b6250}li{margin:2px 0}@page{margin:18mm}</style></head><body>${$('#actaDoc').innerHTML}</body></html>`);
  w.document.close(); setTimeout(() => w.print(), 400);
};
$('#actaTrasladar').onclick = async () => {
  const destino = $('#actaDestino').value, p = paneles.find(x => x.id === destino);
  if (!destino || !p) return;
  if (!await confirmar(`¿Llevar esta acta al ${p.nombre}? Si tiene una sesión abierta se anexará a ella; si no, se abrirá una sesión para deliberarla.`, 'Llevar')) return;
  try {
    const r = await api(`/api/sesiones/${actaSesion.id}/trasladar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ panel_id: destino }) });
    $('#dlgActa').close(); $('#dlgSesiones').close();
    await cargar(destino);
    avisar(r.anexada ? `Acta anexada a la sesión nº ${r.sesion.numero} del ${p.nombre}.` : `Abierta la sesión nº ${r.sesion.numero} del ${p.nombre} para deliberar el acta.`);
  } catch (e) { avisar(e.message, true); }
};

// ---- registro de sesiones ----
async function abrirRegistro() {
  $('#regPanel').innerHTML = '<option value="">Todos los consejos</option>' + paneles.map(p => `<option value="${p.id}">${esc(p.nombre)}</option>`).join('');
  $('#dlgSesiones').showModal(); pintarRegistroSesiones();
}
async function pintarRegistroSesiones() {
  const q = new URLSearchParams(); if ($('#regPanel').value) q.set('panel', $('#regPanel').value); if ($('#regEstado').value) q.set('estado', $('#regEstado').value);
  const lista = await api('/api/sesiones?' + q).catch(() => []);
  const estado = s => s.estado === 'cerrada' ? '<em class="s-chip">Cerrada</em>' : `<em class="s-chip vivo">${s.estado === 'votacion' ? 'En votación' : 'En curso'}</em>`;
  $('#regCuerpo').innerHTML = !lista.length ? '<p class="ayuda" style="text-align:center;padding:30px 0">No hay sesiones registradas con este filtro.</p>' :
    `<table class="tabla reg"><thead><tr><th>Consejo · sesión</th><th>Asunto</th><th>Inicio</th><th>Cierre</th><th>Estado</th><th></th></tr></thead><tbody>${lista.map(s => `
      <tr><td><b>${esc(s.panel)}</b><small>Sesión nº ${s.numero} · ${s.consultas} consulta${s.consultas === 1 ? '' : 's'}</small></td>
      <td class="asunto">${esc(s.asunto)}${s.resultado ? `<small>${esc(s.resultado.texto)}</small>` : ''}</td>
      <td>${fechaHora(s.abierta)}</td><td>${s.cerrada ? fechaHora(s.cerrada) : '—'}</td><td>${estado(s)}</td>
      <td class="acc">${s.tiene_acta ? `<button type="button" class="enlace peq" data-acta="${s.id}">${ico('sello')}<span>Acta</span></button>` : ''}
        ${s.estado !== 'cerrada' ? `<button type="button" class="enlace peq" data-ir="${s.panel_id}">${ico('flecha')}<span>Ir</span></button>` : ''}
        <button type="button" class="icono" data-del="${s.id}" title="Eliminar del registro">${ico('papelera')}</button></td></tr>`).join('')}</tbody></table>`;
  $('#regCuerpo').querySelectorAll('[data-acta]').forEach(b => b.onclick = () => verActa(+b.dataset.acta));
  $('#regCuerpo').querySelectorAll('[data-ir]').forEach(b => b.onclick = async () => { $('#dlgSesiones').close(); await cargar(b.dataset.ir); });
  $('#regCuerpo').querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    if (!await confirmar('¿Eliminar esta sesión del registro, con su transcripción, votaciones y acta? No se puede deshacer.', 'Eliminar')) return;
    try { await api(`/api/sesiones/${b.dataset.del}`, { method: 'DELETE' }); pintarRegistroSesiones(); if (panel) cargar(panel.id); }
    catch (e) { avisar(e.message, true); }
  });
}
$('#regPanel').onchange = $('#regEstado').onchange = pintarRegistroSesiones;
$('#abrirSesiones').onclick = abrirRegistro;

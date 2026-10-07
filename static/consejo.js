const $ = s => document.querySelector(s);
let paneles = [], panel = null, msgs = [], sel = null, estado = {}, adjuntos = [], qActual = null, aviso = '';
const ES_DOC = f => /\.(pdf|docx|txt|md|odt|rtf)$/i.test(f.name);

const api = async (url, opt) => {
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.status === 204 ? null : r.json();
};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function md(t) {  // markdown mínimo, siempre sobre texto escapado
  const lineas = esc(t).split('\n'); let h = '', lista = false;
  const en = x => x.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
  for (const l of lineas) {
    const li = l.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (li) { if (!lista) { h += '<ul>'; lista = true; } h += `<li>${en(li[1])}</li>`; continue; }
    if (lista) { h += '</ul>'; lista = false; }
    if (l.trim()) h += `<p>${en(l.replace(/^#+\s*/, ''))}</p>`;
  }
  return h + (lista ? '</ul>' : '');
}

async function cargar(id) {
  paneles = await api('/api/paneles');
  panel = paneles.find(p => p.id === id) || paneles[0] || null;
  if (panel) localStorage.panel = panel.id;
  msgs = panel ? await api(`/api/paneles/${panel.id}/mensajes`) : [];
  sel = null; estado = {}; aviso = '';
  const ult = [...msgs].reverse().find(m => m.rol === 'user');
  qActual = ult ? ult.pregunta_id : null;
  for (const m of msgs) if (m.rol === 'agent' && m.pregunta_id === qActual)
    estado[m.agente_id] = m.error ? 'error' : 'listo';
  pintarTabs(); pintarArco(); pintarMesa(); pintarRegistro();
}
async function refrescarAgentes() {   // recuentos de pools, sin tocar la conversación
  const ps = await api('/api/paneles'); const p = ps.find(x => panel && x.id === panel.id);
  if (p) { panel.agentes = p.agentes; pintarArco(); }
}

function pintarTabs() {
  $('#paneles').innerHTML = '';
  for (const p of paneles) {
    const b = document.createElement('button');
    b.className = 'ghost' + (panel && p.id === panel.id ? ' act' : '');
    b.textContent = p.nombre; b.onclick = () => cargar(p.id);
    $('#paneles').append(b);
  }
}

function pintarArco() {
  const arco = $('#arco'); arco.innerHTML = '';
  if (!panel) return;
  const W = arco.clientWidth, H = arco.clientHeight, n = panel.agentes.length;
  const cx = W / 2, cy = H - 40;
  const Rx = Math.max(160, W / 2 - 70), Ry = Math.max(160, H - 170);
  $('#descripcion').textContent = aviso || panel.descripcion || '';
  const mesaW = Math.min(640, W * (W < 700 ? .92 : .6)); let top = 12;
  panel.agentes.forEach((a, i) => {
    const t = n === 1 ? Math.PI / 2 : Math.PI * (0.9 - 0.8 * i / (n - 1));
    const x = cx + Rx * Math.cos(t), y = cy - Ry * Math.sin(t);
    if (Math.abs(x - cx) < mesaW / 2 + 56) top = Math.max(top, y + 66);
    $('#mesa').style.setProperty('--mesa-top', Math.min(top, H - 260) + 'px');
    const d = document.createElement('div');
    d.className = 'agente ' + (estado[a.id] || '') + (sel === a.id ? ' sel' : '');
    d.style.cssText = `left:${x}px;top:${y}px;--c:${a.color}`;
    d.innerHTML = `<div class="avatar">${esc(a.emoji)}</div><div class="n">${esc(a.nombre)}</div><div class="r">${esc(a.rol)}</div>`
      + (a.capitulos ? `<div class="pool" title="${a.docs} documentos · ${a.capitulos} capítulos">📚 ${a.capitulos}</div>` : '');
    d.onclick = () => { sel = a.id; pintarArco(); pintarMesa(); };
    arco.append(d);
  });
}

function pintarMesa() {
  const r = $('#respuesta'); r.className = ''; r.style.removeProperty('--c');
  const a = panel && panel.agentes.find(x => x.id === sel);
  if (!a) {
    r.className = 'vacia';
    r.innerHTML = 'Haz una pregunta al consejo.<br><small>Cada experto responderá desde su especialidad. Pulsa uno para leer su respuesta.</small>';
    return;
  }
  r.style.setProperty('--c', a.color);
  const suyos = msgs.filter(x => x.rol === 'agent' && x.agente_id === a.id && x.pregunta_id === qActual)
                    .sort((p, q) => p.ronda - q.ronda);
  let h = `<div class="quien">${esc(a.emoji)} ${esc(a.nombre)} · ${esc(a.rol)}</div>`;
  for (const m of suyos) {
    if (m.ronda > 0) h += `<div class="replica">💬 Réplica ${m.ronda}</div>`;
    h += md(m.texto);
    if (m.fuentes.length) h += '<div class="fuentes">📚 ' + m.fuentes.map(f =>
      `<span>${esc(f.doc)} · cap. ${f.capitulo}: ${esc(f.titulo)}</span>`).join('') + '</div>';
  }
  if (estado[a.id] === 'pensando') h += `<p><i>Pensando…</i></p>`;
  else if (!suyos.length) h += '<p>Aún no ha respondido.</p>';
  r.innerHTML = h;
  if (suyos.some(m => m.error)) r.classList.add('error');
}

function pintarRegistro() {
  const box = $('#registro'); box.innerHTML = '';
  if (!panel) return;
  for (const m of msgs) {
    const a = panel.agentes.find(x => x.id === m.agente_id);
    const d = document.createElement('div');
    d.className = 'm ' + m.rol; if (a) d.style.setProperty('--c', a.color);
    d.innerHTML = `<div class="q">${m.rol === 'user' ? 'Tú' : esc(a ? a.nombre : 'Agente')}${m.ronda ? ' · réplica ' + m.ronda : ''}</div>`
      + (m.rol === 'user' ? `<p style="margin:0;white-space:pre-wrap">${esc(m.texto)}</p>` : md(m.texto))
      + m.adjuntos.map(x => `<div class="chip">📄 ${esc(x.nombre)}</div>`).join(' ')
      + m.imagenes.map(i => `<img src="/img/${i}">`).join('');
    box.append(d);
  }
  box.scrollTop = box.scrollHeight;
}

// ---- enviar ----
function pintarAdjuntos() {
  $('#adjuntos').innerHTML = '';
  adjuntos.forEach((f, i) => {
    const d = document.createElement('div');
    if (ES_DOC(f)) { d.className = 'chip'; d.innerHTML = `📄 ${esc(f.name)} <b>×</b>`; d.querySelector('b').onclick = () => { adjuntos.splice(i, 1); pintarAdjuntos(); }; }
    else { d.className = 'mini'; d.innerHTML = `<img src="${URL.createObjectURL(f)}"><b>×</b>`; d.querySelector('b').onclick = () => { adjuntos.splice(i, 1); pintarAdjuntos(); }; }
    $('#adjuntos').append(d);
  });
}
$('#archivos').onchange = e => { adjuntos.push(...e.target.files); e.target.value = ''; pintarAdjuntos(); };
$('#chat').addEventListener('paste', e => {
  const fs = [...e.clipboardData.files].filter(f => f.type.startsWith('image/'));
  if (fs.length) { adjuntos.push(...fs); pintarAdjuntos(); }
});
$('#texto').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chat').requestSubmit(); }
});
$('#texto').addEventListener('input', e => { e.target.style.height = 'auto'; e.target.style.height = e.target.scrollHeight + 'px'; });
$('#dialogo').checked = localStorage.dialogo === '1';
$('#rondas').value = localStorage.rondas || '1';
const sincDialogo = () => { $('#lrondas').hidden = !$('#dialogo').checked; localStorage.dialogo = $('#dialogo').checked ? '1' : '0'; localStorage.rondas = $('#rondas').value; };
$('#dialogo').onchange = $('#rondas').onchange = sincDialogo; sincDialogo();

$('#chat').onsubmit = async e => {
  e.preventDefault();
  if (!panel || !panel.agentes.length || $('#enviar').disabled) return;
  const fd = new FormData(); fd.append('texto', $('#texto').value);
  adjuntos.forEach(f => fd.append('imagenes', f));
  const nR = $('#dialogo').checked ? +$('#rondas').value : 0;
  $('#enviar').disabled = true; $('#enviar').textContent = adjuntos.some(ES_DOC) ? 'Procesando documentos…' : 'Preguntando…';
  try {
    const q = await api(`/api/paneles/${panel.id}/preguntas`, { method: 'POST', body: fd });
    $('#texto').value = ''; $('#texto').style.height = 'auto'; adjuntos = []; pintarAdjuntos();
    msgs.push(q); qActual = q.pregunta_id; estado = {}; sel = null;
    const pid = panel.id, vigente = () => panel && panel.id === pid && qActual === q.pregunta_id;
    let activos = panel.agentes.map(a => a.id);
    for (let r = 0; r <= nR && activos.length; r++) {
      aviso = r ? `💬 Diálogo: réplica ${r} de ${nR}` : '';
      activos.forEach(id => estado[id] = 'pensando');
      pintarArco(); pintarMesa(); pintarRegistro();
      const hechos = await Promise.all(activos.map(async id => {
        let m;
        try { m = await api(`/api/preguntas/${q.pregunta_id}/agentes/${id}?ronda=${r}`, { method: 'POST' }); }
        catch (err) { m = { rol: 'agent', agente_id: id, pregunta_id: q.pregunta_id, ronda: r, texto: String(err), error: true, imagenes: [], adjuntos: [], fuentes: [] }; }
        if (!vigente()) return null;
        msgs.push(m); estado[id] = m.error ? 'error' : 'listo';
        if (!sel) sel = id;
        pintarArco(); pintarMesa(); pintarRegistro();
        return m;
      }));
      if (!vigente()) return;
      activos = hechos.filter(m => m && !m.error).map(m => m.agente_id);
    }
    aviso = ''; pintarArco();
  } catch (err) { alert(err.message); }
  $('#enviar').disabled = false; $('#enviar').textContent = 'Preguntar';
};

// ---- lateral ----
$('#historial').onclick = () => { $('#lateral').hidden = !$('#lateral').hidden; pintarRegistro(); };
$('#cerrar').onclick = () => $('#lateral').hidden = true;
$('#vaciar').onclick = async () => {
  if (!confirm('¿Vaciar la conversación de este panel? (los pools no se tocan)')) return;
  await api(`/api/paneles/${panel.id}/mensajes`, { method: 'DELETE' }); cargar(panel.id);
};

// ---- pools por agente ----
let poolAg = null, poolDatos = {}, poolTimer = null, abiertos = new Set();
const VIVO = e => !['listo', 'error'].includes(e);
async function abrirPools() {
  if (!panel) return;
  poolAg = panel.agentes.some(a => a.id === poolAg) ? poolAg : (panel.agentes[0] || {}).id;
  $('#pools').showModal();
  const s = await api('/salud').catch(() => ({}));
  $('#notaPools').classList.toggle('aviso', !s.fabrica_configurada);
  if (!s.fabrica_configurada) $('#notaPools').textContent = '⚠ Falta CONSEJO_FABRICA_URL en el .env: sin la fábrica no se pueden procesar documentos.';
  await cargarPools();
}
async function cargarPools() {
  clearTimeout(poolTimer);
  if (!$('#pools').open || !panel) return;
  poolDatos = await api(`/api/paneles/${panel.id}/pools`).catch(() => poolDatos);
  pintarPools();
  if ((poolDatos[poolAg] || []).some(d => VIVO(d.estado))) poolTimer = setTimeout(cargarPools, 2000);
  else refrescarAgentes();
}
function pintarPools() {
  const tabs = $('#poolsTabs'); tabs.innerHTML = '';
  for (const a of panel.agentes) {
    const b = document.createElement('button'); b.className = 'ghost' + (a.id === poolAg ? ' act' : '');
    b.style.setProperty('--c', a.color);
    b.textContent = `${a.emoji} ${a.nombre} (${(poolDatos[a.id] || []).length})`;
    b.onclick = () => { poolAg = a.id; pintarPools(); }; tabs.append(b);
  }
  const cuerpo = $('#poolsCuerpo'), a = panel.agentes.find(x => x.id === poolAg);
  if (!a) { cuerpo.innerHTML = '<p class="nota">Este panel no tiene agentes.</p>'; return; }
  cuerpo.innerHTML = `<div class="zona" id="zona">Biblioteca de <b>${esc(a.nombre)}</b> · arrastra aquí PDF, DOCX, TXT, MD, ODT o RTF
    <br><button id="subirPool" type="button">+ Añadir documentos</button><input id="filePool" type="file" multiple hidden accept=".pdf,.docx,.txt,.md,.odt,.rtf"></div><div id="listaDocs"></div>`;
  const zona = $('#zona');
  $('#subirPool').onclick = () => $('#filePool').click();
  $('#filePool').onchange = e => subirPool(e.target.files);
  zona.ondragover = e => { e.preventDefault(); zona.classList.add('sobre'); };
  zona.ondragleave = () => zona.classList.remove('sobre');
  zona.ondrop = e => { e.preventDefault(); zona.classList.remove('sobre'); subirPool(e.dataTransfer.files); };
  const lista = $('#listaDocs');
  for (const d of poolDatos[a.id] || []) {
    const el = document.createElement('div'); el.className = 'doc';
    const cls = d.estado === 'listo' ? 'listo' : d.estado === 'error' ? 'error' : 'vivo';
    el.innerHTML = `<div class="t"><b>📄 ${esc(d.nombre)}</b><span class="estado ${cls}">${esc(d.estado === 'listo' ? d.capitulos + ' capítulos' : d.paso || d.estado)}</span>
      ${d.capitulos ? '<button class="ghost" data-a="indice">Índice</button>' : ''}
      ${d.estado === 'listo' || d.estado === 'error' ? '<button class="ghost" data-a="re" title="Volver a procesar">↻</button>' : ''}
      <button class="ghost" data-a="del" title="Quitar del pool">🗑</button></div>
      ${d.error ? `<div class="err">${esc(d.error)}</div>` : ''}<div class="caps" hidden></div>`;
    el.querySelector('[data-a=del]').onclick = async () => { if (confirm(`¿Quitar «${d.nombre}» del pool?`)) { await api(`/api/docs/${d.id}`, { method: 'DELETE' }); cargarPools(); } };
    const re = el.querySelector('[data-a=re]'); if (re) re.onclick = async () => { try { await api(`/api/docs/${d.id}/reprocesar`, { method: 'POST' }); } catch (e) { alert(e.message); } cargarPools(); };
    const ix = el.querySelector('[data-a=indice]'); if (ix) ix.onclick = () => indice(d, el.querySelector('.caps'));
    if (abiertos.has(d.id)) indice(d, el.querySelector('.caps'), true);
    lista.append(el);
  }
  if (!(poolDatos[a.id] || []).length) lista.innerHTML = '<p class="nota">Aún no hay documentos. Lo que subas aquí solo lo consulta este agente.</p>';
}
async function indice(d, caja, forzar) {
  if (!forzar && !caja.hidden) { caja.hidden = true; abiertos.delete(d.id); return; }
  abiertos.add(d.id); caja.hidden = false;
  const r = await api(`/api/docs/${d.id}/capitulos`);
  caja.innerHTML = r.capitulos.map(c => `<details data-id="${c.id}"><summary>${c.orden}. ${esc(c.titulo)} <em>· ${c.n} car.${c.simplificado ? '' : ' · extracto'}</em></summary>
    <div class="res">${esc(c.resumen)}${c.claves ? `<br><i>${esc(c.claves)}</i>` : ''}</div><pre hidden></pre></details>`).join('');
  caja.querySelectorAll('details').forEach(x => x.ontoggle = async () => {
    const pre = x.querySelector('pre'); if (!x.open || pre.textContent) return;
    pre.textContent = (await api(`/api/capitulos/${x.dataset.id}`)).texto; pre.hidden = false;
  });
}
async function subirPool(files) {
  if (!files.length) return;
  const fd = new FormData(); [...files].forEach(f => fd.append('archivos', f));
  try { await api(`/api/paneles/${panel.id}/agentes/${poolAg}/docs`, { method: 'POST', body: fd }); }
  catch (e) { alert(e.message); }
  cargarPools();
}
$('#abrirPools').onclick = abrirPools;
$('#cerrarPools').onclick = () => $('#pools').close();
$('#pools').onclose = () => clearTimeout(poolTimer);

// ---- editor ----
const COLORES = ['#8b9cff', '#4fd1a5', '#f6b45c', '#ff7aa2', '#6ec1ff', '#c792ea', '#ffd166', '#ef8354'];
let editando = null;
function filaAgente(a = {}) {
  const d = document.createElement('div'); d.className = 'ag'; d.dataset.id = a.id || '';
  const c = a.color || COLORES[$('#listaAgentes').children.length % COLORES.length];
  d.innerHTML = `
    <label>Icono<input class="emoji" maxlength="4" value="${esc(a.emoji || '🙂')}"></label>
    <label>Nombre<input class="nombre" value="${esc(a.nombre || '')}"></label>
    <label>Rol<input class="rol" value="${esc(a.rol || '')}"></label>
    <label>Color<input class="color" type="color" value="${c}"></label>
    <button type="button" class="ghost" title="Quitar (también su pool)">✕</button>
    <label class="ancho">Instrucciones (personalidad, especialidad, cómo responde)
      <textarea class="instr" rows="2">${esc(a.instrucciones || '')}</textarea></label>
    <label class="ancho">Modelo propio (opcional — vacío usa el del servidor; para imágenes, uno con visión)
      <input class="modelo" value="${esc(a.modelo || '')}"></label>`;
  d.querySelector('button').onclick = () => { if (!a.capitulos || confirm(`${a.nombre} tiene ${a.capitulos} capítulos en su pool: se borrarán al guardar. ¿Quitarlo?`)) d.remove(); };
  $('#listaAgentes').append(d);
}
function abrirEditor(p) {
  editando = p; const f = $('#formEditor');
  $('#tituloEditor').textContent = p ? 'Editar panel' : 'Nuevo panel';
  f.nombre.value = p ? p.nombre : ''; f.descripcion.value = p ? p.descripcion : '';
  f.contexto.value = p ? p.contexto : 'Sois un consejo de expertos. Respondéis en español, de forma breve y desde vuestra especialidad.';
  $('#listaAgentes').innerHTML = '';
  (p ? p.agentes : [{}, {}, {}]).forEach(filaAgente);
  $('#eliminar').style.display = p ? '' : 'none';
  $('#editor').showModal();
}
$('#nuevo').onclick = () => abrirEditor(null);
$('#editar').onclick = () => panel && abrirEditor(panel);
$('#addAgente').onclick = () => filaAgente();
$('#cancelar').onclick = () => $('#editor').close();
$('#eliminar').onclick = async () => {
  if (!confirm(`¿Eliminar "${editando.nombre}", su conversación y los pools de sus agentes?`)) return;
  await api(`/api/paneles/${editando.id}`, { method: 'DELETE' }); $('#editor').close(); cargar();
};
$('#formEditor').onsubmit = async e => {
  e.preventDefault(); const f = e.target;
  const agentes = [...$('#listaAgentes').children].map(d => ({
    id: d.dataset.id || undefined, emoji: d.querySelector('.emoji').value, nombre: d.querySelector('.nombre').value,
    rol: d.querySelector('.rol').value, color: d.querySelector('.color').value,
    instrucciones: d.querySelector('.instr').value, modelo: d.querySelector('.modelo').value }));
  const cuerpo = JSON.stringify({ nombre: f.nombre.value, descripcion: f.descripcion.value, contexto: f.contexto.value, agentes });
  const h = { 'Content-Type': 'application/json' };
  const p = editando ? await api(`/api/paneles/${editando.id}`, { method: 'PUT', headers: h, body: cuerpo })
                     : await api('/api/paneles', { method: 'POST', headers: h, body: cuerpo });
  $('#editor').close(); cargar(p.id);
};

window.addEventListener('resize', pintarArco);
cargar(localStorage.panel);

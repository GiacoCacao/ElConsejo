# El Consejo

Panel visual de **expertos (agentes IA)**. Cada panel reúne varios agentes colocados en arco, cada
uno con su nombre, rol e instrucciones; una barra de chat en el centro permite preguntarles a
todos a la vez. Se pueden adjuntar imágenes y documentos, activar un **diálogo** para que los
expertos repliquen entre sí y dar a cada agente su propia **biblioteca** (pool) de documentos.

## Qué hace

- **Paneles y agentes** configurables (nombre, rol, icono, color, instrucciones, modelo propio y contexto común).
- **Chat central**: la pregunta llega a todos los agentes en paralelo; se pulsa un agente para leer su respuesta.
- **Diálogo entre expertos** (conmutador, 1–3 réplicas): tras responder, cada agente lee lo que dijeron sus
  colegas y replica con su postura final.
- **Imágenes** (las ven los modelos con visión) y **documentos** (PDF, DOCX, TXT, MD, ODT, RTF) en el chat: el
  texto lo extrae la [fábrica de documentos](#fábrica) (con OCR si está escaneado) y se pasa a los agentes.
- **Pools por agente** (📚 Pools): cada documento subido a la biblioteca de un agente se envía a la fábrica,
  se **divide en capítulos**, se **simplifica** (resumen y palabras clave con IA), se **ordena** y se
  **indexa** (SQLite FTS5 + búsqueda semántica de la fábrica). Al responder, el agente recibe solo los
  capítulos pertinentes y cita de qué documento y capítulo sale cada dato.

## Paneles de serie

Se crean una sola vez al arrancar (`paneles_base.py`); si se borran, no vuelven: **Empresarial**,
**Marketing y Ventas**, **Técnico Moderno**, **Psicológico**, **Financiero**, **Filosófico** (con
materialismo filosófico y teología, entre otras escuelas) e **Importaciones a Venezuela**, con seis
expertos cada uno.

## Puesta en marcha

```bash
cp .env.ejemplo .env && chmod 600 .env     # rellena CONSEJO_IA_CLAVE y CONSEJO_FABRICA_URL
# edita TU_IP en docker-compose.ejemplo.yml
docker compose -f docker-compose.ejemplo.yml up -d --build
curl http://TU_IP:8190/salud
```

| Variable | Para qué |
|---|---|
| `CONSEJO_IA_URL` / `CONSEJO_IA_MODELO` / `CONSEJO_IA_CLAVE` | endpoint compatible con OpenAI. Para analizar imágenes hace falta un modelo con visión (se puede fijar por agente) |
| `CONSEJO_FABRICA_URL` / `CONSEJO_FABRICA_CLAVE` | fábrica de documentos (obligatoria para PDF/pools) |

## Fábrica

Los documentos se procesan con una *fábrica de documentos* externa que expone `POST /documentos`,
`GET /documentos/{id}`, `GET /documentos/{id}/texto`, `GET /buscar` y `DELETE /documentos/{id}`.
Sin ella, el chat y los pools funcionan con imágenes y texto, pero no con documentos.

## API (resumen)

`GET/POST /api/paneles` · `PUT/DELETE /api/paneles/<id>` · `GET/DELETE /api/paneles/<id>/mensajes` ·
`POST /api/paneles/<id>/preguntas` (multipart: `texto`, `imagenes`) ·
`POST /api/preguntas/<id>/agentes/<agente>?ronda=N` · `GET /api/paneles/<id>/pools` ·
`POST /api/paneles/<id>/agentes/<agente>/docs` · `GET /api/docs/<id>/capitulos` · `DELETE /api/docs/<id>`.

## Desarrollo

Flask + SQLite, interfaz sin build en `static/`. Pruebas con la fábrica y la IA simuladas:

```bash
pip install -r requirements.txt pytest && python -m pytest -q
```

No incluye autenticación: pensado para una red privada (p. ej. Tailscale).

## Créditos

- Fondo: *United Nations Headquarters — Security Council chamber, straight-on view*, foto de
  [Jdforrester](https://commons.wikimedia.org/wiki/File:United_Nations_Headquarters_-_Security_Council_chamber,_straight-on_view.jpg),
  licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Adaptada: recortada, virada a tonos cálidos y oscurecida.
- Tipografías Cormorant Garamond e Inter, SIL Open Font License 1.1 (`static/fuentes/LICENCIAS.txt`).

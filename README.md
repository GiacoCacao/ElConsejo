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

## Tiempo real y consultor general

- **Respuestas en tiempo real**: el texto de cada experto aparece mientras lo escribe (flujo de la API; el
  servidor reenvía los trozos como líneas JSON). Si la conexión se corta a mitad, se conserva lo dicho.
- **Consultor general**: asesor interno fuera del hemiciclo, en un panel lateral. Aclara palabras, conceptos,
  siglas y referencias (definición, sentido en el contexto, ejemplo, términos relacionados) sin opinar sobre el
  asunto. Se puede **seleccionar un término** en una respuesta, la transcripción o un acta y pulsar «Consultar».
  Su historial se guarda en el navegador; su gasto cuenta en el consumo del panel.

## Sesiones, votación y actas

- **Sesión**: cada asunto se trata en una sesión numerada por consejo (botón *Iniciar sesión*; si se consulta sin
  sesión, se abre una con la pregunta como asunto). Se fija el **orden del debate**: *por turnos* (cada experto
  interviene en su turno y oye a quienes hablaron antes) o *simultáneo*.
- **Deliberar acuerdo**: *acuerdo unificado* (la Secretaría —una IA neutral— redacta una propuesta que integra las
  posturas; se aprueba si nadie vota en contra y, si no, se revisa con las objeciones) o *mayoría simple* (la
  Secretaría identifica las alternativas del debate y gana la más votada; un empate lo decide el voto de calidad
  de la presidencia). Pantalla de votación con escaños, recuento y explicación de voto.
- **Acta de cierre**: los datos objetivos (asistentes, orden, consultas, votos, acuerdo literal) los compone el
  código; la IA solo redacta la síntesis del debate y las conclusiones, a partir de la transcripción. Se puede
  imprimir, descargar en Markdown y **llevar a otro consejo**: se anexa a su sesión abierta o abre una sesión
  para deliberarla. Las actas anexas llegan a los expertos como contexto.
- **Registro de sesiones** de todos los consejos, con estado, resultado y acceso al acta.

## Seguridad y administración (Ajustes)

- **Acceso**: con `CONSEJO_CLAVE_PRESIDENCIA` la sala pide clave (control total); `CONSEJO_CLAVE_OBSERVADOR` da acceso
  de solo lectura. Sesión de 30 días, cookie firmada con `CONSEJO_SECRETO`, bloqueo tras 5 intentos fallidos.
- **Tope de gasto** diario y mensual en dólares: *avisar* o *bloquear* las llamadas a la IA al alcanzarlo.
- **Copias de seguridad** diarias de la base de datos (copia en caliente de SQLite) en `datos/copias`, rotativas,
  descargables desde Ajustes.
- Los expertos y la Secretaría conocen la **fecha y hora actuales** y advierten cuando su información puede estar
  desactualizada.

## Consumo y costes

Una barra en la sala muestra el servicio y su franja tarifaria, el contexto usado (máximo de los
expertos en la última consulta), los tokens y el coste aproximado; al pulsarla se ve el detalle por
experto, por panel, por bibliotecas y global. El coste sale de los tokens que informa la API (`usage`)
y de la tabla de tarifas (USD por millón de tokens), que se puede editar y ampliar con otros modelos.
Las de DeepSeek vienen de serie, con su precio doble en hora punta (01–04 y 06–10 UTC, lunes a viernes).

## Paneles de serie

Se crean una sola vez al arrancar (`paneles_base.py`); si se borran, no vuelven: **Empresarial**,
**Marketing y Ventas**, **Técnico Moderno**, **Psicológico**, **Financiero**, **Filosófico** (con
materialismo filosófico y teología, entre otras escuelas) **Importaciones a Venezuela**, **Político**, **Militar**, **Internacionalistas y Diplomáticos**,
**Periodistas**, **Diseño Gráfico**, **Infraestructura IT**, **Electrónica**, **Electricidad**, **Jurídico** y **Científico**, con seis
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
| `CONSEJO_IA_URL` / `CONSEJO_IA_MODELO` / `CONSEJO_IA_CLAVE` / `CONSEJO_IA_PENSAR` | endpoint compatible con OpenAI. Por defecto `deepseek-flash` (con visión). `CONSEJO_IA_PENSAR=1` activa el razonamiento de DeepSeek |
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

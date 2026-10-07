"""Configuración desde variables de entorno (el .env del despliegue)."""
import os

DATOS = os.environ.get("CONSEJO_DATOS", "/datos")
IMG = os.path.join(DATOS, "img")
DB = os.path.join(DATOS, "consejo.db")

IA_URL = os.environ.get("CONSEJO_IA_URL", "https://api.deepseek.com/v1").rstrip("/")
IA_MODELO = os.environ.get("CONSEJO_IA_MODELO", "deepseek-flash")
IA_CLAVE = os.environ.get("CONSEJO_IA_CLAVE", "")
# DeepSeek razona antes de responder si no se le dice lo contrario: más lento y caro para dictámenes breves
IA_PENSAR = os.environ.get("CONSEJO_IA_PENSAR", "0") == "1"

FABRICA_URL = os.environ.get("CONSEJO_FABRICA_URL", "").rstrip("/")
FABRICA_CLAVE = os.environ.get("CONSEJO_FABRICA_CLAVE", "")

# Acceso: sin CONSEJO_CLAVE_PRESIDENCIA la sala queda abierta a toda la red (como antes)
CLAVE_PRESIDENCIA = os.environ.get("CONSEJO_CLAVE_PRESIDENCIA", "")
CLAVE_OBSERVADOR = os.environ.get("CONSEJO_CLAVE_OBSERVADOR", "")
SECRETO = os.environ.get("CONSEJO_SECRETO", "")   # firma la cookie de sesión
COPIAS = os.path.join(DATOS, "copias")
COPIAS_GUARDAR = int(os.environ.get("CONSEJO_COPIAS", "14"))   # cuántas copias diarias se conservan
TZ = "America/Caracas"

MAX_IMG = 8 * 1024 * 1024
MAX_DOC = 50 * 1024 * 1024
HISTORIAL = 8          # turnos previos que ve cada agente
MAX_RONDAS = 3         # réplicas máximas en el diálogo
EXT_IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
EXT_DOC = {".pdf", ".docx", ".txt", ".md", ".odt", ".rtf"}

os.makedirs(IMG, exist_ok=True)

# Configuración del cerebro documental DTR — sistema MERCANTIL
import os

RAIZ_DATOS = "K:\\"                      # SOLO LECTURA. Jamás escribir aquí.
CARPETA_CEREBRO = r"C:\dtr-brain"        # Salida del cerebro
BRAIN_DIR = os.path.join(CARPETA_CEREBRO, "brain")
EXPEDIENTES_DIR = os.path.join(BRAIN_DIR, "expedientes")
META_DIR = os.path.join(BRAIN_DIR, "_meta")
DB_PATH = os.path.join(META_DIR, "index.db")
MANIFEST_PATH = os.path.join(META_DIR, "manifest.json")
GRAPH_PATH = os.path.join(META_DIR, "graph.json")
LOG_PATH = os.path.join(META_DIR, "sync.log")

# Extensiones de las que se extrae texto completo
EXT_TEXTO = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm",
             ".xlsx", ".eml", ".msg"}

# Extensiones que entran al mapa como ficha (nombre+ruta+metadatos) sin texto
EXT_FICHA = {".doc", ".xls", ".wbk", ".rtf", ".odt",
             ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp",
             ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".mp3", ".wav", ".m4a",
             ".dwg", ".zip", ".rar", ".7z", ".pptx", ".ppt"}

# Todo lo demás (dll, tmp, conf, css, dat, ...) se ignora por completo.

# Carpetas excluidas del recorrido (en cualquier nivel)
DIRS_EXCLUIDOS = {"$recycle.bin", "system volume information", ".git",
                  "node_modules", "__pycache__"}

# Límites de robustez
MAX_TEXTO_CHARS = 1_500_000     # texto máximo almacenado por documento
MAX_PDF_PAGINAS = 1500          # páginas máximas a extraer por PDF
MAX_PDF_BYTES = 300 * 1024**2   # PDFs mayores: solo ficha
MAX_XLSX_FILAS = 300            # filas por hoja
MIN_TEXTO_PDF = 80              # menos chars => "escaneado(ocr?)"
EXTRACTO_PALABRAS = 40
MAX_FRAGMENTOS_MD = 400         # fragmentos clave por expediente
MAX_ARISTAS_POR_EXP = 40

# Grafo: tokens ignorados al derivar nombres de cliente.
# Incluye vocabulario jurídico genérico: una carpeta temática llamada
# "Concursos" o "Tasacion Costas" no debe generar aristas con todo el corpus.
STOPWORDS_GRAFO = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u",
                   "a", "en", "al", "sl", "sa", "slu", "sll", "sc", "cb",
                   "sau", "scp", "sccl", "vs", "sr", "sra", "don", "dona",
                   "otros", "otro", "varios", "grupo", "the", "and",
                   "expediente", "asunto", "contra", "iberia", "studio",
                   "espana", "spain", "consulting", "servicios", "gestion",
                   # términos jurídicos/administrativos genéricos
                   "concurso", "concursos", "concursal", "herencia",
                   "herencias", "banco", "bancos", "demanda", "demandas",
                   "divorcio", "divorcios", "escaner", "escrito", "escritos",
                   "jura", "cuenta", "cuentas", "tasacion", "tasaciones",
                   "costa", "costas", "apelacion", "recurso", "recursos",
                   "ejecucion", "sentencia", "sentencias", "contrato",
                   "contratos", "doctrina", "jurisprudencia", "libro",
                   "libros", "modelo", "modelos", "foto", "fotos",
                   "factura", "facturas", "cliente", "clientes",
                   "procedimiento", "procedimientos", "querella",
                   "querellas", "laboral", "mercantil", "civil", "penal",
                   "honorarios", "minuta", "minutas", "juzgado", "juzgados",
                   "nota", "notas", "guarda", "custodia", "satisfaccion",
                   "extraprocesal", "preliminares", "diligencias",
                   "accidente", "accidentes", "trafico", "traficos",
                   "informe", "informes", "despacho", "archivo", "carta",
                   "cartas", "correo", "correos", "reclamacion", "prueba",
                   "pruebas", "conclusiones", "audiencia", "presupuesto"}

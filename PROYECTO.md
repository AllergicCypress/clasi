# Clasificador Automático de Archivos

## Contexto y Motivación

Este proyecto nació de la experiencia práctica de organizar la carpeta `~/Downloads` de un usuario con ~200 archivos acumulados. El proceso manual tomó horas y reveló patrones repetibles que justifican automatización.

**Problema central:** los archivos se acumulan sin estructura porque clasificarlos en el momento requiere interrumpir el flujo de trabajo. El costo de organizarlos después es alto porque hay que recordar o redescubrir el contexto de cada archivo.

**Meta inmediata:** automatizar la organización de `~/Downloads`.  
**Meta siguiente:** extender la herramienta a `~/` completo, con todos los controles de seguridad que eso requiere.  
**Meta final:** una herramienta universal que funcione en cualquier equipo, aprenda de la estructura de carpetas que el usuario ya tiene, y se adapte automáticamente a nuevos temas conforme aparecen — sin configuración manual profunda.

---

## Principio de diseño central

> **La estructura de carpetas existente ES la configuración.**

El usuario no escribe reglas para cada tema. El usuario organiza carpetas (como lo hace naturalmente). La herramienta lee esas carpetas, aprende qué tipo de contenido vive en cada una, y lleva los archivos nuevos al lugar que les corresponde.

Las reglas manuales (`hints.yaml`) solo existen para casos que el descubrimiento automático no puede inferir: duplicados por nombre, instaladores por extensión, excepciones especiales.

```
Antes: usuario escribe reglas → herramienta las sigue
Ahora: usuario organiza carpetas → herramienta aprende de ellas
```

---

## Lecciones aprendidas

### Sesión de prueba — 2026-06-16 (~200 archivos reales)

1. **La extracción de texto clasifica ~75% de archivos automáticamente.** `pdftotext` y la lectura del XML interno de DOCX/XLSX son suficientes para identificar la mayoría de documentos académicos.

2. **El 25% restante son PDFs escaneados o archivos sin nombre descriptivo.** Requieren OCR o revisión manual. Este porcentaje no desaparece — se gestiona, no se elimina.

3. **El contexto del usuario es insustituible.** Un archivo llamado `1.pdf` solo es clasificable si sabes que el usuario cursa Ecuaciones Diferenciales. Las reglas deben derivarse del contexto, no hardcodearse.

4. **Los duplicados son frecuentes y predecibles.** Archivos con `(1)`, `(2)` en el nombre son casi siempre duplicados de descarga.

5. **La ejecución sobre `~/` es cualitativamente diferente a `~/Downloads`.** Sin exclusiones estrictas, la herramienta puede romper el sistema.

6. **Un catálogo legible es más útil que un log técnico.** El formato tabla (archivo | contenido detectado | destino sugerido) fue inmediatamente útil.

7. **Los archivos `_merged` no son duplicados — su original sí lo es.** Un archivo `X_merged.pdf` contiene a `X.pdf`. La herramienta debe detectar el par y marcar el original como redundante.

8. **Las carpetas temáticas se crean cuando hay densidad suficiente.** Si se detectan >7 archivos de un mismo tema sin carpeta existente → crear carpeta. Si ≤7 → reportar sin mover.

### Revisión arquitectónica — 2026-06-17

9. **Las reglas hardcodeadas presuponen la estructura del usuario y generan redundancia.** Si `rules.yaml` dice "Métodos Numéricos → ~/Downloads/Métodos Numéricos/" pero el usuario ya tiene `~/Métodos Numéricos/`, se crean dos carpetas del mismo tema. La solución es que las reglas describan *contenido*, no *destinos*.

10. **El descubrimiento dinámico de carpetas hace la herramienta verdaderamente universal.** Si el usuario crea una carpeta nueva ("Termodinámica"), la próxima ejecución ya la conoce y puede enrutar archivos hacia ella sin tocar ningún archivo de configuración.

11. **Un documento que MENCIONA un tema no pertenece a él.** El scorer debe distinguir entre un archivo cuyo nombre está relacionado con una carpeta (señal fuerte) y uno cuyo cuerpo solo menciona el tema (señal débil). Solución: penalizar cuando el stem del archivo no aporta tokens coincidentes con el nombre de la carpeta.

12. **El índice debe ser global y recursivo, no local al directorio.** Al ejecutar sobre `~/`, la herramienta debe descubrir todas las carpetas temáticas en todo el árbol de directorios (dentro de los límites de exclusiones), no solo las inmediatas. De lo contrario, `~/Downloads/Ecuaciones Diferenciales/` es invisible al escanear `~/`.

13. **Las carpetas fuera de su sitio son un problema tan real como los archivos fuera de su sitio.** Una carpeta `Cálculo` dentro de `~/Downloads/` cuando debería estar en `~/Documents/` genera fragmentación silenciosa. El flujo correcto es: el archivo va a la carpeta temática correcta (donde sea que esté), y la herramienta sugiere reubicar la carpeta si detecta que no está en el lugar óptimo.

14. **Dos carpetas con el mismo nombre normalizado son una carpeta.** Si existen `~/Downloads/Cálculo/` y `~/Documents/Calculo/`, son el mismo tema con fragmentación accidental. La herramienta debe detectarlas, elegir la ubicación canónica, y proponer unificarlas — moviendo el contenido de la "peor" hacia la "mejor".

### Revisión arquitectónica — 2026-06-20 (REV-001, ver `Revisiones_1.2.md`)

15. **No toda carpeta existente es un tema — algunas son contenedores administrativos.** El principio "la estructura existente es la configuración" asumía que cualquier carpeta indexable representa un tema. Carpetas como `Universidad`, `Trabajo`, `Documentos`, `Importante` agrupan por contexto (quién, dónde, cuándo), no por contenido, y si se indexan degradan el descubrimiento con cada ejecución (atraen archivos no relacionados → su vocabulario se vuelve más heterogéneo → atraen aún más). Solución: etapa de categorización antes de indexar (`_categoria_carpeta` en `discovery.py`) que descarta contenedoras vía lista negra (`config/carpetas_genericas.yaml`) y homogeneidad de contenido entre archivos muestreados (Jaccard promedio, `UMBRAL_HOMOGENEIDAD = 0.15`).

16. **La homogeneidad de contenido NO debe exigirse en subcarpetas narrow (profundas).** Primer intento de la heurística aplicó la prueba de homogeneidad a todas las carpetas, sin distinguir profundidad. Resultado: `ACTIVIDAD 5.3`, `PAPC1.3`, `2.2`, `EU4` — destinos correctos y ya validados en pruebas reales — cayeron por debajo del umbral y se excluyeron del índice. La causa: en esas carpetas, el archivo encaja por **coincidencia de nombre** (`ACTIVIDAD 5.3.xlsx` → carpeta `ACTIVIDAD 5.3`), no por tema de contenido, así que sus archivos pueden ser heterogéneos entre sí sin que eso invalide la carpeta como destino. Solución: la prueba de homogeneidad solo aplica hasta `MAX_PROFUNDIDAD_HOMOGENEIDAD = 2` niveles desde la raíz escaneada; más profundo, se asume temática por diseño (igual que las carpetas con nombre estructural, exentas sin importar la profundidad). Verificado con `clasi sim ~/Documents`: mismos 7 archivos con destino / 12 sin destino y mismos scores (0.70–0.79) que la prueba real documentada en sesiones previas — cero regresión.

---

## Arte previo — herramientas similares

### `organize` (tfeldmann) — el referente más cercano

- **Repositorio:** https://github.com/tfeldmann/organize · **PyPI:** `pip install organize-tool`
- **Qué es:** CLI en Python, open source, reglas en YAML, con `sim` (dry-run) y `run` (ejecutar).
- **Qué hace bien:** filtros por nombre, extensión, fecha, texto de PDF/DOCX; detección de duplicados por hash; `filter_mode: any/all`; profundidad configurable (`min_depth`, `max_depth`); regex con grupos nombrados que se convierten en variables; sin catch-all forzado (archivos sin match se dejan en lugar).
- **Qué NO hace:** descubrimiento dinámico de carpetas, OCR para PDFs escaneados, carpetas por densidad, detección de pares `_merged`, universalidad entre equipos.
- **Por qué no usarlo como base:** sus rutas destino son hardcodeadas por regla — exactamente el problema que queremos evitar.

### Lo que adoptamos de su diseño

| Decisión | Origen | Aplicación en `clasi` |
|---|---|---|
| `filter_mode: any/all` | `organize` | OR/AND entre filtros de la misma regla |
| `min_depth` / `max_depth` | `organize` | Control de profundidad en el scanner |
| Regex con grupos → variables | `organize` | Extracción de metadatos del contenido |
| Sin catch-all forzado | `organize` | Archivos sin match → reportar, no mover |
| `on_conflict` por acción | `organize` | `skip`, `rename_new`, `rename_existing` |

---

## Requisitos

### Funcionales

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| F1 | Extraer texto y metadatos de todos los tipos de archivo comunes | Alta |
| F2 | Descubrir automáticamente carpetas existentes y aprender de su contenido | Alta |
| F3 | `clasi sim <directorio>`: mostrar qué movería sin mover nada | Alta |
| F4 | `clasi run <directorio>`: mover archivos según el motor de descubrimiento | Alta |
| F5 | Registrar cada operación en un log para poder revertirla | Alta |
| F6 | `clasi undo`: revertir la última ejecución | Alta |
| F7 | Generar catálogo de archivos no clasificados | Media |
| F8 | OCR como fallback para PDFs sin texto extraíble | Media |
| F9 | Revisión interactiva en terminal para archivos ambiguos | Media |
| F10 | Detectar duplicados por nombre (`(1)`, `(2)`) y pares redundantes `_merged` | Media |
| F11 | Crear carpeta temática automáticamente cuando >7 archivos sin carpeta destino | Media |
| F12 | Exclusiones configurables (carpetas, patrones, rutas absolutas) | Alta |
| F13 | Resolución de conflictos configurable por tipo: `skip`, `rename_new`, `rename_existing` | Alta |
| F14 | Soporte de `filter_mode: any/all` por regla de hints | Media |
| F15 | Profundidad de escaneo configurable (`max_depth`) | Media |
| F16 | Descubrimiento recursivo global: índice de todas las carpetas temáticas del sistema | Alta |
| F17 | Detección de carpetas duplicadas (mismo nombre normalizado en distintas rutas) | Alta |
| F18 | Elección de carpeta canónica por prioridad de ubicación padre | Alta |
| F19 | `clasi merge`: unificar carpetas duplicadas en la canónica con log reversible | Alta |
| F20 | `clasi move-folder`: reubicar una carpeta a un lugar más apropiado | Media |
| F21 | Sugerencias en `sim`: advertir carpetas duplicadas y carpetas en ubicación subóptima | Alta |

### No funcionales

| ID | Requisito |
|----|-----------|
| NF1 | **Seguridad:** nunca tocar `.git/`, `.config/`, `.ssh/` y similares por defecto |
| NF2 | **Idempotencia:** ejecutar dos veces produce el mismo resultado |
| NF3 | **Transparencia:** siempre mostrar qué hace y por qué |
| NF4 | **Sin destructividad:** mover, nunca eliminar |
| NF5 | **Portabilidad:** funcionar en Linux sin configuración previa del usuario |
| NF6 | **Universalidad:** adaptarse a la estructura de carpetas de cualquier equipo sin reescribir reglas |
| NF7 | **Auto-actualización del conocimiento:** nueva carpeta creada por el usuario → disponible en la siguiente ejecución sin tocar ningún archivo de configuración |

---

## Arquitectura

### Descubrimiento global y resolución de conflictos de carpetas

#### Descubrimiento recursivo

El índice se construye recorriendo **todo el árbol de directorios** dentro del alcance permitido (respetando exclusiones), no solo el nivel inmediato del directorio objetivo. Esto permite que al ejecutar sobre `~/`, la herramienta conozca `~/Downloads/Ecuaciones Diferenciales/`, `~/Documents/Métodos Numéricos/`, etc.

#### Normalización de nombres de carpeta

Para detectar duplicados, todos los nombres se normalizan con `normalizar_nombre()`:
```
"Métodos Numéricos"  →  "metodosnumericos"
"Metodos_Numericos"  →  "metodosnumericos"
"METODOS NUMERICOS"  →  "metodosnumericos"
```
Proceso: quitar acentos → minúsculas → eliminar espacios, `_` y `-`.
Esta clave se usa como índice del diccionario en `construir_indice()`.

#### Filtrado de duplicados: criterios para que sea "real"

No toda coincidencia de nombre normalizado es un duplicado temático. Se descartan:

1. **Relaciones padre-hijo**: `Ecuaciones Diferenciales/` y su hijo `ECUACIONES DIFERENCIALES/` son la misma carpeta con distinto case, no duplicados.
2. **Nombres estructurales de curso**: `UNIDAD 1`, `EXAMEN`, `CAPTURAS`, `ACTIVIDAD 2.4` aparecen por diseño en cada materia — no son duplicados reales. Se detectan con `_PATRON_ESTRUCTURAL` + nombres con < 5 letras.
3. **Subcarpetas profundas** (> 4 niveles): `UNIDAD1/CAPTURAS` vs `UNIDAD5/CAPTURAS` son la misma estructura repetida por diseño.

#### Carpeta canónica — prioridad de ubicación

Cuando se detectan dos o más carpetas con el mismo nombre normalizado, se elige una como **canónica** usando este orden de prioridad:

| Prioridad | Ubicación padre | Razón |
|---|---|---|
| 1 | `~/Documents/` o `~/Documentos/` | Hogar semántico de documentos |
| 2 | `~/` (raíz del home) | Accesible, visible |
| 3 | Cualquier otra carpeta de usuario | Neutro |
| 4 | `~/Downloads/` | Transitoria por naturaleza |

En caso de empate, gana la carpeta con **más archivos** (es la establecida).

#### Comportamiento ante carpetas duplicadas

```
Situación: "Cálculo" existe en ~/Downloads/ Y en ~/Documents/

clasi sim:
  → Elige ~/Documents/Cálculo/ como canónica (prioridad 1 > 4)
  → Los archivos nuevos van a ~/Documents/Cálculo/
  → Muestra advertencia:
    ⚠ CARPETA DUPLICADA: "Cálculo"
      Canónica:   ~/Documents/Cálculo/        (3 archivos)
      Redundante: ~/Downloads/Cálculo/         (1 archivo)
      Sugerencia: unificar con `clasi merge`

clasi run:
  → Mueve los archivos a la canónica
  → Pregunta al usuario si quiere unificar las carpetas ahora

clasi merge:
  → Mueve el contenido de la redundante a la canónica
  → Registra en log (reversible con undo)
  → Informa si la carpeta redundante quedó vacía (el usuario decide si la elimina)
```

#### Comportamiento ante carpeta en lugar subóptimo (sin duplicado)

```
Situación: "Cálculo" solo existe en ~/Downloads/

clasi sim:
  → Los archivos van a ~/Downloads/Cálculo/ (es lo que hay)
  → Muestra sugerencia:
    💡 SUGERENCIA: La carpeta "Cálculo" está en ~/Downloads/ (transitoria).
       Podría vivir mejor en ~/Documents/. Usa `clasi move-folder` para reubicarla.

clasi move-folder "Cálculo":
  → Mueve ~/Downloads/Cálculo/ → ~/Documents/Cálculo/
  → Registra en log (reversible)
```

### Tres capas

```
┌─────────────────────────────────────────────────────────────┐
│  CAPA 1 — MOTOR DE DESCUBRIMIENTO                           │
│                                                             │
│  - Recorre carpetas existentes en el directorio objetivo    │
│  - Extrae semántica de: nombre de carpeta + muestra de      │
│    contenido de archivos que ya viven ahí                   │
│  - Construye índice dinámico:                               │
│    { "Métodos Numéricos": { ruta, keywords, score_model } } │
│  - Se reconstruye en cada ejecución → siempre actualizado   │
└─────────────────────┬───────────────────────────────────────┘
                      │ índice de carpetas conocidas
┌─────────────────────▼───────────────────────────────────────┐
│  CAPA 2 — MOTOR DE CLASIFICACIÓN                            │
│                                                             │
│  Para cada archivo a procesar:                              │
│  1. Extraer texto / metadatos (según tipo de archivo)       │
│  2. Puntuar contra cada entrada del índice (TF-IDF simple)  │
│  3. Si score > umbral → candidato destino                   │
│  4. Aplicar hints.yaml para casos especiales                │
│     (duplicados, instaladores, extensiones específicas)     │
│  5. Sin candidato + >7 del mismo tema → proponer carpeta    │
│  6. Sin candidato + ≤7 → reportar, no mover                 │
└─────────────────────┬───────────────────────────────────────┘
                      │ lista de decisiones
┌─────────────────────▼───────────────────────────────────────┐
│  CAPA 3 — MOTOR DE EJECUCIÓN                                │
│                                                             │
│  - `clasi sim`: muestra tabla de decisiones sin actuar      │
│  - `clasi run`: ejecuta movimientos, escribe log JSON Lines  │
│  - `clasi undo`: revierte desde el log más reciente         │
│  - Resolución de conflictos por regla                       │
└─────────────────────────────────────────────────────────────┘
```

### Flujo detallado

```
[Directorio objetivo]
        │
        ▼
[0. DESCUBRIMIENTO — nuevo]
  - Itera subcarpetas (no archivos)
  - Por cada carpeta: extrae nombre + keywords de muestra de contenido
  - Construye índice: carpeta → vector de keywords
  - Detecta pares (X.pdf, X_merged.pdf) entre archivos sueltos
        │ índice
        ▼
[1. ESCANEO]
  - Lista archivos sueltos en el directorio (respetando exclusiones)
  - max_depth configurable (default: 1 para ~/, null para ~/Downloads)
  - Salta symlinks
        │ lista de archivos
        ▼
[2. EXTRACCIÓN]
  - PDF con texto  → pdftotext / PyMuPDF
  - PDF escaneado  → OCR Tesseract [Fase 3]
  - DOCX           → word/document.xml
  - XLSX           → xl/sharedStrings.xml
  - PPTX           → ppt/slides/*.xml
  - TXT/MD/CSV     → lectura directa
  - Imágenes       → EXIF + OCR [Fase 3]
  - Audio          → tags ID3/Vorbis (título, álbum, artista)
  - Vídeo          → metadatos ffprobe (título, descripción)
  - Código fuente  → primera línea + detección de lenguaje
  - Archivos ZIP   → listado de contenido interno
  - EPUB           → content.opf (título, autor, materia)
  - Desconocidos   → magic bytes + nombre de archivo
        │ texto / metadatos
        ▼
[3. CLASIFICACIÓN]
  - Score TF-IDF simple: texto del archivo vs keywords de cada carpeta
  - Aplica hints.yaml (casos especiales: duplicados, extensiones)
  - Devuelve: { archivo, destino, confianza, método }
        │ decisiones
        ▼
[4. PRESENTACIÓN — clasi sim]
  - Tabla: archivo | destino | confianza | método de clasificación
  - Marca sin candidato como [SIN DESTINO] — no [REVISAR]
  - Muestra propuestas de carpetas nuevas (tema + count)
        │ confirmación del usuario
        ▼
[5. EJECUCIÓN — clasi run]
  - Mueve archivos
  - Crea carpetas nuevas si es necesario
  - Escribe log JSON Lines
        │
        ▼
[6. UNDO]
  - Lee log más reciente
  - Invierte cada operación
```

### Estructura de archivos del proyecto

```
clasificador-archivos/
├── PROYECTO.md
├── src/
│   ├── discovery.py     ← índice dinámico de carpetas; scoring TF-IDF con penalización
│   ├── scanner.py       ← recorre directorio, aplica exclusiones, salta symlinks
│   ├── extractor.py     ← extrae texto/metadatos según tipo de archivo
│   ├── classifier.py    ← hints primero, luego descubrimiento TF-IDF
│   ├── executor.py      ← mueve archivos, log JSON Lines, undo
│   └── cli.py           ← clasi sim | run | undo  [merge | move-folder en Fase 2]
├── config/
│   ├── hints.yaml             ← casos especiales sin semántica temática (v3)
│   ├── exclusions.yaml        ← carpetas y patrones a ignorar
│   └── carpetas_genericas.yaml ← nombres de carpetas contenedoras (no temáticas, REV-001)
├── logs/
│   └── .gitkeep
├── tests/
└── requirements.txt
```

---

## Soporte de tipos de archivo

| Categoría | Formatos | Método de extracción | Fase |
|---|---|---|---|
| Documentos con texto | PDF (con texto), DOCX, XLSX, PPTX, ODT, ODS | pdftotext / XML interno | 1 |
| Texto plano | TXT, MD, CSV, LOG, RTF | lectura directa | 1 |
| PDF escaneado | PDF sin capa de texto | OCR Tesseract | 3 |
| Imágenes | JPG, PNG, WEBP, TIFF, RAW | EXIF + OCR | 3 |
| Audio | MP3, FLAC, OGG, WAV, M4A, AAC | tags ID3/Vorbis (mutagen) | 2 |
| Vídeo | MP4, MKV, AVI, MOV, WEBM | metadatos ffprobe | 2 |
| Código fuente | PY, JAVA, JS, TS, C, CPP, GO, RS, HTML, SQL | primera línea + detección de lenguaje | 2 |
| Comprimidos | ZIP, TAR, GZ, RAR, 7Z | listado de contenido interno | 2 |
| Ebooks | EPUB | content.opf (título, autor, materia) | 2 |
| Desconocidos | cualquier extensión no listada | magic bytes + nombre de archivo | 1 |

---

## Formato de hints.yaml

`hints.yaml` reemplaza a `rules.yaml`. Su alcance es limitado: solo cubre los casos que el descubrimiento automático no puede inferir por sí solo (casos especiales sin semántica temática).

```yaml
version: 3

hints:

  # Duplicados por nombre — el descubrimiento no puede inferir esto del contenido
  - nombre: duplicados_descarga
    filter_mode: any
    filtros:
      - nombre_contiene: [" (1)", " (2)", " (3)", ".crdownload"]
    accion_especial: marcar_duplicado
    conflicto: rename_new

  # Instaladores — clasificación por extensión, no por tema
  - nombre: instaladores
    filtros:
      - extension: [".exe", ".msi", ".run", ".deb", ".rpm", ".AppImage"]
    accion_especial: carpeta_especial
    nombre_carpeta: Software_Instaladores
    conflicto: skip

  # Imágenes sin contexto temático
  - nombre: imagenes_sueltas
    filtros:
      - extension: [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"]
    accion_especial: carpeta_especial
    nombre_carpeta: Imágenes_Generales
    conflicto: rename_new
```

**Lo que YA NO está en hints.yaml:**
- Rutas destino hardcodeadas (`~/Downloads/Métodos Numéricos/`)
- Nombres de temas académicos o temáticos
- Cualquier cosa que el descubrimiento de carpetas pueda inferir solo

---

## Formato de exclusiones (exclusions.yaml)

```yaml
version: 1

# Carpetas que nunca se tocan (por nombre exacto, en cualquier nivel)
carpetas_exactas:
  # Sistema y configuración
  - .git
  - .config
  - .local
  - .ssh
  - .gnupg
  - .cache
  - .mozilla
  - .thunderbird
  - .var
  - snap
  - node_modules
  - __pycache__
  # Entornos de desarrollo
  - .cargo
  - .dotnet
  - .java
  - .m2
  - .netbeans
  - .npm
  - .vscode
  - .vscode-shared
  - .electron-gyp
  # Herramientas y agentes
  - .claude
  - .codex
  - .agents
  - .kiro
  - .pi
  - .aws
  - .pki
  - .windows
  # Apps de usuario
  - .minecraft
  - .steam
  - .spicetify
  - .zen

# Archivos que nunca se tocan (por patrón glob)
patrones_nombre:
  - "*.sock"
  - "*.pid"
  - "*.lock"
  - "*.env"
  - "*.log"
  - "*.bak"
  - "desktop.ini"
  - "thumbs.db"
  - ".DS_Store"
  - ".gitignore"
  - ".bash_history"
  - ".bash_logout"
  - ".bash_profile"
  - ".bashrc"
  - ".python_history"
  - ".XCompose"
  - ".pulse-cookie"
  - ".claude.json"
  - "*.desktop"

# Rutas absolutas que nunca se tocan
rutas_absolutas:
  - ~/Proyectos/clasificador-archivos
  - ~/Proyectos
  - ~/Projects
  - ~/NetBeansProjects
  - ~/Ethernal_MOD
  - ~/.local/share/omarchy
```

---

## Fases de desarrollo

### Fase 1 — MVP de Downloads ✦ (completada)
Objetivo: replicar lo que hicimos manualmente, pero ejecutable en cualquier momento.

**Decisiones de interfaz que sientan la base de todas las fases:**
- El directorio objetivo es siempre un argumento: `clasi run <directorio>`
- Las hints son siempre un archivo externo: `--hints <ruta>`
- Las exclusiones están activas desde el día 1: `--exclusions <ruta>`

**Entregables:**
- [x] `config/exclusions.yaml` — lista completa de exclusiones basada en la estructura real del home
- [x] `config/hints.yaml` — casos especiales v3 (reemplaza rules.yaml; migración completada en Fase 1)
- [x] `src/extractor.py` — extrae texto de PDF (pdftotext), DOCX y XLSX (XML interno)
- [x] `src/scanner.py` — lista archivos en el directorio dado, aplica exclusiones, salta symlinks
- [x] `src/classifier.py` — clasificación en dos etapas: hints primero, luego descubrimiento TF-IDF
- [x] `src/executor.py` — mueve archivos con resolución de conflictos, log JSON Lines, undo
- [x] `src/cli.py` — subcomandos `clasi sim`, `clasi run`, `clasi undo`
- [x] `requirements.txt` — click, pyyaml, rich
- [x] Instalar dependencias: `sudo pacman -S python-click python-yaml python-rich`
- [x] Prueba real sobre `~/Downloads` — herramienta funciona correctamente
- [x] Prueba sobre `~/` — encontrados y corregidos 2 bugs (symlinks, .bash_logout)

**Criterio de éxito:** ✅ `clasi sim ~/Downloads` y `clasi sim ~/` funcionan correctamente.

### Fase 2 — Motor de descubrimiento global + unificación de carpetas
Objetivo: índice recursivo, detección de carpetas duplicadas o mal ubicadas, y tipos de archivo extendidos.

- [x] `src/discovery.py` — índice de carpetas con scoring TF-IDF y penalización por match solo de contenido
- [x] Clasificador basado en TF-IDF contra el índice (umbral 0.40, configurable)
- [x] Migrar `rules.yaml` → `hints.yaml` (solo casos especiales)
- [x] Descubrimiento recursivo: índice global de todas las carpetas temáticas del sistema
- [x] Normalización de nombres de carpeta para detección de duplicados (`normalizar_nombre()`)
- [x] Elección de carpeta canónica por prioridad de ubicación (Documents > ~/ > otras > Downloads)
- [x] `clasi sim`: advertencias de carpetas duplicadas y sugerencias de reubicación
- [x] `max_depth` como argumento CLI (`--max-depth`, default 4)
- [x] Categorización de carpetas (temática/contenedora) previa al índice — REV-001: lista negra (`carpetas_genericas.yaml`) + homogeneidad de contenido acotada por profundidad (`MAX_PROFUNDIDAD_HOMOGENEIDAD = 2`)
- [ ] `clasi merge`: unificar carpetas duplicadas en la canónica (con log y undo)
- [ ] `clasi move-folder`: reubicar una carpeta a un lugar más apropiado
- [ ] Soporte de tipos: audio (mutagen), vídeo (ffprobe), código fuente, ZIP, EPUB
- [ ] Detección de pares redundantes `(X.pdf, X_merged.pdf)`
- [ ] Creación automática de carpeta temática cuando >7 archivos sin destino existente
- [ ] `clasi catalog`: catálogo markdown de archivos procesados

### Fase 3 — OCR, revisión interactiva y confianza
Objetivo: clasificar el 25% de archivos que Fase 2 no puede resolver solo.

- [ ] OCR con Tesseract para PDFs escaneados e imágenes
- [ ] Revisión interactiva: muestra archivo, texto extraído, candidato destino → usuario confirma
- [ ] Umbral de confianza configurable (solo mover si score ≥ X)
- [ ] Soporte EXIF para imágenes (organización por fecha/cámara)
- [ ] Filtro `python` para lógica personalizada avanzada (inspirado en `organize`)

### Fase 4 — Universalidad y despliegue en cualquier equipo
Objetivo: que cualquier usuario pueda instalar `clasi` y usarlo sin configuración manual.

- [ ] Instalación limpia: `pip install clasi` → funciona inmediatamente
- [ ] `clasi init`: escanea el equipo, genera `exclusions.yaml` adaptado al sistema detectado
- [ ] Soporte recursivo completo con `max_depth` configurable
- [ ] Detección de tipo de carpeta (proyecto de código, config del sistema) para no desorganizar
- [ ] Tests de regresión antes de ejecutar en home
- [ ] Documentación de usuario

---

## Métricas de éxito

| Métrica | Objetivo |
|---------|----------|
| Archivos clasificados automáticamente (Fase 1) | ≥ 75% |
| Archivos clasificados automáticamente (Fase 2+) | ≥ 90% |
| Falsos positivos (archivos mal clasificados) | < 5% |
| Archivos movidos que se pueden revertir | 100% |
| Tiempo de ejecución sobre ~/Downloads (~200 archivos) | < 30 segundos |
| Nueva carpeta creada por usuario → disponible sin reconfiguración | 100% |
| Funciona en equipo nuevo sin editar ningún archivo de configuración | ✓ |

---

## Decisiones pendientes

- [x] **Lenguaje de implementación** — Python. Dependencias: pdfplumber o PyMuPDF, python-docx, click, pyyaml, rich.
- [x] **Nombre del comando CLI** — `clasi`.
- [x] **Formato de log** — JSON Lines. Una línea por operación, reversible de forma independiente.
- [x] **Interfaz de revisión interactiva** — `rich` para tablas en terminal (Fase 1); evaluar `textual` en Fase 3.
- [x] **Resolución de conflictos** — `skip`, `rename_new`, `rename_existing`. Nunca sobreescribir.
- [x] **Estructura del YAML de reglas** — migrar a `hints.yaml` en Fase 2; solo casos especiales sin semántica temática.
- [x] **Algoritmo de clasificación** — TF-IDF simple contra índice de carpetas existentes. Sin modelo ML externo.
- [x] **Umbral de confianza TF-IDF** — 0.40. Calibrado para evitar falsos positivos por "mención" vs "pertenencia". Configurable en CLI con `--umbral`.
- [x] **Penalización por match solo de contenido** — si el stem del archivo no aporta ningún token que coincida con la carpeta, el score se multiplica por 0.35. Previene que documentos que MENCIONAN un tema sean clasificados como pertenecientes a él.
- [x] **Categorización de carpetas (REV-001)** — `UMBRAL_HOMOGENEIDAD = 0.15` (Jaccard promedio entre archivos muestreados, mínimo 3 muestras) y `MAX_PROFUNDIDAD_HOMOGENEIDAD = 2`. Ambos provisionales: calibrados solo con la prueba real sobre `~/Documents`; pendiente recalibrar con más estructuras de usuario.
- [ ] **Nombre del subcomando de inicialización** — `clasi init`, `clasi setup`, ¿otro?

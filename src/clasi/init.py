"""
Generador de exclusions.yaml adaptado al sistema detectado.
Lógica de detección separada del CLI para facilitar pruebas.
"""

from datetime import date
from pathlib import Path


# ── Exclusiones base (siempre presentes) ─────────────────────────────────────

_CARPETAS_SISTEMA = [
    ".git", ".config", ".local", ".ssh", ".gnupg", ".cache",
    ".mozilla", ".thunderbird", ".var",
]

_CARPETAS_DESARROLLO_BASE = [
    "node_modules", "__pycache__",
]

_CARPETAS_DESTINOS_HINTS = [
    "Software_Instaladores", "Imágenes_Generales", "Comprimidos",
    "Temporales_Duplicados", "PDF_Texto_Corrupto",
]

_PATRONES_BASE = [
    "*.sock", "*.pid", "*.lock", "*.env", "*.log", "*.bak",
    "desktop.ini", "thumbs.db", ".DS_Store", ".gitignore",
    ".bash_history", ".bash_logout", ".bash_profile", ".bashrc",
    ".python_history", ".XCompose", ".pulse-cookie", ".claude.json",
    "*.desktop",
]

# Herramientas opcionales: detectadas solo si la carpeta existe en ~
_HERRAMIENTAS = [
    (".cargo",         "Rust (cargo)"),
    (".npm",           "Node.js (npm)"),
    (".m2",            "Java (Maven)"),
    (".gradle",        "Java (Gradle)"),
    (".dotnet",        ".NET"),
    (".java",          "Java JDK"),
    (".netbeans",      "NetBeans"),
    (".vscode",        "VS Code"),
    (".vscode-shared", "VS Code (extensiones compartidas)"),
    (".electron-gyp",  "Electron"),
    (".aws",           "AWS CLI"),
    (".pki",           "PKI / certificados"),
    (".steam",         "Steam"),
    (".minecraft",     "Minecraft"),
    (".spicetify",     "Spicetify"),
    (".zen",           "Zen Browser"),
    (".windows",       "Wine / Windows compat"),
    (".claude",        "Claude CLI"),
    (".codex",         "Codex"),
    (".agents",        "Agentes varios"),
    (".kiro",          "Kiro"),
    (".pi",            "Pi"),
    ("snap",           "Snap packages"),
]

# Nombres de directorios en ~ que suelen ser raíces de proyectos de código
_NOMBRES_DIRS_PROYECTO = [
    "Proyectos", "Projects", "repos", "Repos", "code", "Code",
    "dev", "Dev", "develop", "Develop", "work", "Work",
    "src", "Src", "workspace", "Workspace", "NetBeansProjects",
]


# ── Detección ─────────────────────────────────────────────────────────────────

def detectar(home: Path | None = None) -> dict:
    """
    Escanea ~ y devuelve un dict con:
      herramientas:   list[(nombre, descripcion)] — detectadas en ~
      dirs_proyecto:  list[Path]                  — directorios de proyectos en ~
    """
    home = (home or Path.home()).expanduser().resolve()

    herramientas = [
        (nombre, desc)
        for nombre, desc in _HERRAMIENTAS
        if (home / nombre).exists()
    ]

    dirs_proyecto = [
        home / nombre
        for nombre in _NOMBRES_DIRS_PROYECTO
        if (home / nombre).is_dir() and not (home / nombre).is_symlink()
    ]

    return {
        "herramientas":  herramientas,
        "dirs_proyecto": dirs_proyecto,
    }


# ── Generación del YAML ───────────────────────────────────────────────────────

def generar_yaml(resultado: dict, home: Path | None = None) -> str:
    """
    Construye el contenido de exclusions.yaml como string formateado.
    Se genera como texto (no yaml.dump) para preservar comentarios y agrupación.
    """
    home = (home or Path.home()).expanduser()
    herramientas  = resultado["herramientas"]
    dirs_proyecto = resultado["dirs_proyecto"]

    lineas = [
        "version: 1",
        f"# Generado por: clasi init ({date.today()})",
        "# Edita este archivo para personalizar las exclusiones en tu sistema.",
        "",
        "# Carpetas que nunca se tocan (por nombre exacto, en cualquier nivel)",
        "carpetas_exactas:",
        "",
        "  # Sistema y configuración",
    ]
    for c in _CARPETAS_SISTEMA:
        lineas.append(f"  - {c}")

    lineas += ["", "  # Desarrollo base"]
    for c in _CARPETAS_DESARROLLO_BASE:
        lineas.append(f"  - {c}")

    if herramientas:
        lineas += ["", "  # Herramientas detectadas en tu sistema"]
        ancho = max(len(n) for n, _ in herramientas)
        for nombre, desc in herramientas:
            padding = " " * (ancho - len(nombre) + 2)
            lineas.append(f"  - {nombre}{padding}# {desc}")

    lineas += [
        "",
        "  # Destinos planos de hints.yaml (nunca son jerarquías temáticas)",
    ]
    for c in _CARPETAS_DESTINOS_HINTS:
        lineas.append(f"  - {c}")

    lineas += [
        "",
        "# Archivos que nunca se tocan (por patrón glob)",
        "patrones_nombre:",
    ]
    for p in _PATRONES_BASE:
        lineas.append(f'  - "{p}"')

    lineas += [
        "",
        "# Rutas absolutas que nunca se tocan",
        "rutas_absolutas:",
    ]
    if dirs_proyecto:
        for ruta in dirs_proyecto:
            try:
                ruta_str = "~/" + str(ruta.relative_to(home))
            except ValueError:
                ruta_str = str(ruta)
            lineas.append(f"  - {ruta_str}")
    else:
        lineas += [
            "  # Añade aquí rutas como ~/Projects o ~/Work si las tienes",
            "  # - ~/Projects",
        ]

    return "\n".join(lineas) + "\n"

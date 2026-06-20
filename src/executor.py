"""Mueve archivos según los resultados del clasificador y escribe el log."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from classifier import Resultado


def resolver_conflicto(destino: Path, politica: str) -> Path:
    if not destino.exists():
        return destino
    if politica == "skip":
        return None
    # renombrar_nuevo: añade sufijo _1, _2, ...
    stem = destino.stem
    sufijo = destino.suffix
    padre = destino.parent
    n = 1
    while True:
        candidato = padre / f"{stem}_{n}{sufijo}"
        if not candidato.exists():
            return candidato
        n += 1


def ejecutar(resultados: list[Resultado], ruta_log: Path, seco: bool = False) -> list[dict]:
    entradas_log = []

    for r in resultados:
        if r.destino is None:
            continue

        destino_final = resolver_conflicto(r.destino / r.archivo.name, r.conflicto)
        if destino_final is None:
            entradas_log.append({
                "accion": "skip",
                "archivo": str(r.archivo),
                "razon": "destino_existe",
                "regla": r.regla,
            })
            continue

        entrada = {
            "accion": "mover",
            "archivo": str(r.archivo),
            "destino": str(destino_final),
            "regla": r.regla,
            "confianza": r.confianza,
            "ts": datetime.now().isoformat(),
        }

        if not seco:
            destino_final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(r.archivo), str(destino_final))

        entradas_log.append(entrada)

    if not seco and entradas_log:
        ruta_log.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta_log, "w") as f:
            for entrada in entradas_log:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    return entradas_log


def deshacer(ruta_log: Path) -> list[dict]:
    if not ruta_log.exists():
        return []

    revertidas = []
    with open(ruta_log) as f:
        operaciones = [json.loads(line) for line in f if line.strip()]

    for op in reversed(operaciones):
        if op["accion"] != "mover":
            continue
        origen = Path(op["destino"])
        destino = Path(op["archivo"])
        if origen.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino))
            revertidas.append(op)

    return revertidas

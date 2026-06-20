# REVISIONES

## Propósito

Este documento recopila debilidades, riesgos arquitectónicos y supuestos cuestionables detectados durante la revisión del diseño de `clasi`.

Su objetivo no es proponer implementaciones definitivas, sino identificar puntos donde la arquitectura podría comportarse incorrectamente al enfrentarse a usuarios, estructuras de directorios o hábitos de organización distintos a los utilizados durante el diseño inicial.

Las revisiones aquí registradas deben considerarse abiertas hasta que exista una solución validada mediante pruebas reales.

---

# REV-001 — La semántica de las carpetas no siempre existe

## Severidad

**CRÍTICA**

## Estado

**Parcialmente resuelta** (implementada en sesión 2026-06-20, ver `PROYECTO.md` § Revisión arquitectónica — 2026-06-20)

### Resumen de la implementación

Se agregó una etapa de categorización (`_categoria_carpeta` en `discovery.py`) que corre antes de construir el índice. Cada carpeta candidata se evalúa así:

1. Nombre estructural (`unidad1`, `actividad5.3`…) → siempre **temática**, sin importar profundidad ni contenido. Ahí el archivo encaja por coincidencia de nombre, no por tema — exigir homogeneidad las penalizaría injustamente (esto se detectó y corrigió durante la implementación: ver punto 2 abajo).
2. Nombre en lista negra (`config/carpetas_genericas.yaml`, ej. `Universidad`, `Documentos`, `Trabajo`, `Varios`) → **contenedora**, no entra al índice.
3. Si no aplica ninguno de los anteriores y la carpeta está a ≤ 2 niveles de la raíz escaneada (`MAX_PROFUNDIDAD_HOMOGENEIDAD`): se mide homogeneidad de contenido (Jaccard promedio entre archivos muestreados, mínimo 3 muestras). Por debajo de `UMBRAL_HOMOGENEIDAD = 0.15` → **contenedora**.
4. En cualquier otro caso → **temática**.

**Validación:** auditado contra `~/Documents` real (no sintético). Primera versión aplicó la prueba de homogeneidad sin distinguir profundidad y generó falsos positivos graves: `ACTIVIDAD 5.3`, `PAPC1.3`, `2.2`, `EU4` —destinos correctos y ya validados en pruebas anteriores— cayeron por debajo del umbral. Se corrigió acotando la prueba a carpetas superficiales (punto 3). Con la corrección, `clasi sim ~/Documents` reproduce exactamente los resultados documentados previamente (7 archivos con destino / 12 sin destino, mismos scores 0.70–0.79) y además excluye correctamente `THE DEEP` (carpeta real con notas personales heterogéneas, sin entrada en la lista negra).

### Por qué "parcialmente" y no "resuelta"

- Los dos umbrales (`UMBRAL_HOMOGENEIDAD`, `MAX_PROFUNDIDAD_HOMOGENEIDAD`) están calibrados con una sola estructura de usuario real. Falta validar contra estructuras de otros usuarios/equipos antes de considerarlos estables (relevante para la meta de universalidad del proyecto).
- La lista negra de `carpetas_genericas.yaml` es estática y en español/inglés común; no se ha probado su cobertura real porque ningún nombre de la lista existe actualmente en `~/Documents` del usuario (la detección de contenedoras observada hasta ahora viene 100% de la homogeneidad, no de la lista negra).
- No hay override manual documentado todavía (preguntas abiertas 4 sigue sin resolver).

## Preguntas abiertas — actualizado

1. ~~¿Cómo medir objetivamente si una carpeta es temática?~~ → Resuelto para v1: homogeneidad de contenido (Jaccard) acotada por profundidad, más lista negra de nombres.
2. ~~¿Qué umbral de homogeneidad debe exigirse?~~ → `0.15`, provisional, calibrado con un solo caso real.
3. ¿Puede una carpeta cambiar de categoría con el tiempo? → Resuelto por diseño: el índice se reconstruye en cada ejecución, así que la categoría se reevalúa siempre con el estado actual.
4. ¿Debe existir intervención manual para corregir clasificaciones? → Sigue abierta. Hoy el único override posible es editar `carpetas_genericas.yaml` a mano.
5. ¿Es suficiente una heurística o se requiere un modelo estadístico? → Heurística suficiente por ahora; sin evidencia de que se necesite más.

## Descripción del problema

El principio fundamental del proyecto establece:

> La estructura de carpetas existente es la configuración.

La arquitectura actual asume que las carpetas existentes representan temas o categorías semánticas útiles.

Ejemplos válidos:

- Métodos Numéricos
- Programación
- Astronomía
- Ruso

En estos casos la carpeta posee:

- nombre descriptivo
- contenido consistente
- identidad temática clara

Por lo tanto puede incorporarse al índice semántico del sistema.

## El supuesto oculto

Actualmente se presupone que:

carpeta existente → tema válido

Pero esta relación no siempre es cierta.

Muchos usuarios organizan información utilizando carpetas genéricas, estructurales o transitorias:

- Universidad
- Trabajo
- Documentos
- Importante
- Pendientes
- PDFs
- Varios

Estas carpetas no representan temas. Representan contenedores.

## Riesgo arquitectónico

Este problema introduce un fenómeno de degradación progresiva:

1. Carpeta genérica entra al índice.
2. Archivos nuevos son enviados a ella.
3. Su contenido se vuelve aún más heterogéneo.
4. El índice aprende información incorrecta.
5. La carpeta atrae todavía más archivos.
6. La precisión disminuye con cada ejecución.

## Reformulación propuesta

La afirmación:

> Las carpetas existentes son la configuración.

debe reformularse como:

> Solo las carpetas que demuestren ser temáticas forman parte de la configuración.

## Hipótesis de solución

Introducir una etapa previa al descubrimiento semántico:

Escaneo → Clasificación de carpetas → Descubrimiento semántico → Clasificación de archivos

### Categorías propuestas

#### Carpeta temática

Representa un área de conocimiento o contenido.

Ejemplos:

- Métodos Numéricos
- Astronomía
- Programación
- Historia

Puede utilizarse como destino y formar parte del índice.

#### Carpeta contenedora

Representa agrupación organizativa.

Ejemplos:

- Universidad
- Trabajo
- Personal
- Documentos

No debe utilizarse como destino semántico.

#### Carpeta estructural

Representa organización interna repetitiva.

Ejemplos:

- Unidad 1
- Unidad 2
- Exámenes
- Capturas
- Tareas

> **Corrección tras implementación (2026-06-20):** la idea original de excluirlas del índice resultó incorrecta. Carpetas como `Unidad 5/ACTIVIDAD 5.3` ya estaban validadas como destino correcto en pruebas reales previas (el archivo encaja por nombre exacto, no por tema). Excluirlas rompía ese comportamiento. Quedan dentro del índice igual que antes; el patrón estructural solo se usa para no reportarlas como "duplicadas" entre materias — ver "Resumen de la implementación" arriba.

(Preguntas abiertas movidas arriba, junto al resumen de la implementación.)

---

# REV-002 — Dependencia excesiva de TF-IDF simple

## Severidad

Alta

## Estado

Abierta

### Problema

TF-IDF funciona bien cuando los temas poseen vocabulario distintivo, pero puede fallar cuando dos dominios comparten gran parte del vocabulario.

### Posibles líneas de investigación

- Embeddings locales
- Sentence Transformers
- Combinación TF-IDF + embeddings
- Scoring híbrido

---

# REV-003 — Ausencia de aprendizaje por corrección del usuario

## Severidad

Media

## Estado

Abierta

### Problema

Actualmente el sistema clasifica archivos pero no aprende de los errores detectados por el usuario.

### Posibles líneas de investigación

- Historial de correcciones
- Ajuste de pesos
- Memoria local de decisiones
- Sistema de retroalimentación incremental

---

# Resumen de prioridad

| ID | Severidad | Prioridad |
|----|-----------|-----------|
| REV-001 | Crítica | 1 |
| REV-002 | Alta | 2 |
| REV-003 | Media | 3 |

La revisión REV-001 debe considerarse el principal riesgo arquitectónico identificado hasta el momento.

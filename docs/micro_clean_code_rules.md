# Constitución Arquitectónica: INES (Monitoreo INES)

### Estándar Unificado de Diseño Micro, Estructura de Backend y Principios Clean Code — Versión 1.0 (Documento MICRO)

Este documento establece el marco normativo micro para la escritura, estructuración y evolución del código fuente en el ecosistema de INES. Integra las necesidades pragmáticas de nuestra arquitectura Django/Python con las directrices universales de *Clean Code* (Robert C. Martin). Su cumplimiento es obligatorio para garantizar un entorno con legibilidad 10/10, libre de degradación tecnológica y óptimo para la co-creación entre desarrolladores humanos e Inteligencia Artificial.

---

## 1. Modularidad: De Monolitos a Paquetes

Cuando un archivo (como `views.py`, `forms.py`, `services.py` o `selectors.py`) supere una extensión crítica ($>250$ líneas) o mezcle múltiples dominios o flujos de negocio, se transformará obligatoriamente en un paquete (carpeta).

* **Estructura por Roles y Contextos:** La división interna de las carpetas debe emular la estructura de las plantillas (*templates*), segmentando la lógica según el contexto del usuario (ej. `admin.py` para flujos administrativos y `user.py` para flujos de beneficiaros regulares).
* **Submódulos Compartidos (`shared.py` / `common.py`):** Si ambos contextos de usuario (`admin.py` y `user.py`) requieren invocar exactamente las mismas funciones o clases de soporte, se centralizarán en un archivo interno llamado `shared.py` (o `common.py`) dentro del mismo paquete.
* **Regla de Acoplamiento Coherente:** El archivo `shared.py` debe ser de bajo nivel. Puede ser importado por `admin.py` y `user.py`, pero `shared.py` **jamás** debe realizar importaciones desde los archivos de roles (evitando estrictamente la importación circular).
* **Exposición Limpia (`__init__.py` vacíos):** El archivo `__init__.py` de los nuevos subpaquetes debe permanecer estrictamente **vacío**. Queda prohibido realizar importaciones implícitas o ascendentes en él. Las importaciones desde otros módulos deben invocar directamente al archivo específico para mantener la trazabilidad.

```python
# CORRECTO
from buildings.views import admin, user
from buildings.views.shared import get_active_equipment

# INCORRECTO (Oculta la procedencia exacta y genera acoplamiento circular)
from buildings import views

```

---

## 2. Anatomía, Orden y Ley del Periódico

Inspirado en la *Metáfora del Periódico*, cada archivo debe leerse como una crónica de prensa: los conceptos abstractos y de alto nivel se sitúan en la parte superior, y los detalles de implementación se desglosan conforme se desciende.

### A. Bloque de Importaciones (Estándar PEP 8 / isort)

Las importaciones deben agruparse con una línea en blanco de separación, ordenadas internamente de forma alfabética:

1. Librerías nativas de Python (ej. `os`, `sys`, `typing`, `decimal`).
2. *Frameworks* y librerías de terceros (ej. `django.shortcuts`, `rest_framework`).
3. Componentes locales y específicos del proyecto INES.

### B. Orden del Bloque de Funciones y Clases (Ciclo CRUD y Narrativa)

Las funciones y métodos públicos principales deben aparecer al inicio. El orden operacional de los bloques debe emular el ciclo de vida natural de los datos (Lectura $\rightarrow$ Destrucción):

1. **Lectura / Consulta:** Vistas de listados (`List`), detalles (`Detail`) o selectores (`selectors.py`).
2. **Escritura / Mutación:** Creación (`Create` / `Add`) y edición (`Update` / `Edit`) mediante servicios (`services.py`).
3. **Destrucción:** Eliminación, desactivación o cancelación (`Delete` / `Cancel`).

---

## 3. Semántica Expresiva y Nombres con Intención

El código debe autodocumentarse a través de nombres precisos. Se prohíbe el uso de comentarios para maquillar código deficiente; si un fragmento requiere explicación, debe refactorizarse.

* **Correspondencia Exacta con el Dominio de Negocio:** El nombre de una función o método debe describir de forma quirúrgica el objeto real del negocio sobre el que opera. Queda estrictamente prohibido usar términos genéricos o incorrectos que generen desinformación sobre el alcance de la acción.
    * **Inexacto (Prohibido):** `process_data()` si la función calcula presión de bomba.
    * **Preciso (Obligatorio):** `calculate_pump_pressure()` o `generate_sensor_payload()` según corresponda.
* **Nombres Reveladores de Intención:** Evitar variables crípticas de un solo carácter. Usar nombres que expliquen el propósito y la unidad de medida si aplica (ej. `elapsed_time_in_days` en lugar de `d`).
* **Evitar la Desinformación y Distinciones Ruidosas:** No incluir el tipo de estructura en el nombre a menos que sea un tipo abstracto estricto (ej. evitar `building_list` si en realidad es un diccionario). No crear entidades con diferencias ambiguas como `SensorData` y `SensorInfo`.
* **Clases y Métodos:** Las clases deben ser sustantivos descriptivos (ej. `BuildingSimulator`, `NotificationService`) y evitar sufijos genéricos como `Manager` o `Data`. Las funciones y métodos deben comenzar obligatoriamente por verbos de acción (ej. `send_alert()`, `calculate_risk_level()`).

---

## 4. Reglas Estrictas para Funciones y Métodos

Para evitar la rigidez y fragilidad del software, las funciones deben ceñirse a las métricas de limpieza de *Uncle Bob*:

* **Responsabilidad Única (*Do One Thing*):** Cada función debe realizar una única tarea y hacerla de forma excelente. No se deben mezclar niveles de abstracción (como reglas de negocio de alto nivel con expresiones regulares de bajo nivel) dentro de la misma función.
* **Tamaño Reducido:** Idealmente, ninguna función de lógica de negocio o vista debe superar las **20 líneas de código útil**.
* **Argumentos Limitados:** El número óptimo de argumentos es $0$. Se aceptan hasta $2$ argumentos. Si una función requiere $3$ o más parámetros, se exige una justificación técnica o la encapsulación de los datos en un objeto intermedio (*Data Transfer Object* - DTO).
* **Sin Efectos Secundarios (*No Side Effects*):** Una función no debe alterar de manera oculta o inesperada el estado global del sistema o de objetos ajenos a su alcance local.

---

## 5. Visibilidad, Encapsulamiento y Funciones Privadas (`_funcion`)

Garantizamos una API interna limpia mediante una estricta política de ocultación de detalles:

* **Identificación:** Toda función de soporte, cálculo intermedio o utilitario requerida exclusivamente por el archivo actual debe comenzar con un guion bajo (ej. `_calculate_vibration_risk`).
* **Ubicación Geográfica:** Las funciones privadas se colocan al final del archivo, situándose inmediatamente debajo de la función pública que las invoca, respetando la proximidad vertical.
* **Migración:** Si una función privada es requerida por otro módulo, se remueve el guion bajo inicial y se evalúa su traslado hacia la capa arquitectónica correcta (`selectors`, `services` o un módulo común `utils.py`).

---

## 6. Tipado Estricto, Calidad Dinámica y Control de Errores

* **Type Hinting Obligatorio:** Para asegurar la asistencia perfecta de IDEs e IAs, todos los argumentos y valores de retorno deben estar explícitamente anotados.
* **Manejo Moderno de Errores:** Se prohíbe el uso de códigos de retorno de error (ej. devolver `-1` o `False` para indicar fallos). Se deben lanzar y capturar excepciones explícitas y semánticas.
* **Prohibición del Valor Nulo (`None`):** Se debe evitar retornar o pasar `None` como un comportamiento normalizado, ya que obliga a la proliferación de validaciones defensivas (`if objeto is not None`). En su lugar, utilícense excepciones o patrones de objeto vacío.
* **Formateo Mecánico Automatizado:** No se discute el formateo en revisiones de código. Se delega en **Ruff** y **Black**. Ningún *commit* se integra sin superar de forma local el Linter y la suite de pruebas unitarias (`pytest`).

---

## 7. Idioma Internacional y Registros (Logs)

* **Código 100% en Inglés:** Toda la sintaxis del proyecto se escribe en inglés técnico. Esto incluye nombres de variables, funciones, clases, métodos, comentarios de código permitidos (ej. TODOs legítimos), nombres de archivos, ramas de Git y mensajes de *commits*.
* **Logs en Inglés:** Los registros del sistema de la aplicación (`logger`) deben redactarse en inglés para facilitar su indexación y análisis en herramientas de observabilidad.
* **Mensajes al Usuario Final en Español (Internacionalización - i18n):** Todo texto, mensaje de error en formularios, descripción de excepciones semánticas o alerta que esté destinado a ser renderizado en las pantallas del usuario **debe escribirse en español** o envolverse obligatoriamente en las funciones de traducción diferida de Django (`gettext_lazy` as `_`).

```python
# CORRECTO: Sintaxis y logs en inglés, mensajes al usuario traducidos/en español
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

def validate_threshold_config(value: float) -> None:
    if value < 0 or value > 100:
        # El log interno ayuda al desarrollador (en inglés)
        logger.warning("Invalid threshold value rejected: %s", value)
        
        # El mensaje de la excepción ayuda al cliente final (en español)
        raise ValidationError(_("El valor del umbral debe estar entre 0 y 100."))

```

---

## Lista de Verificación Pre-Commit (Checklist)

* [ ] ¿La función tiene menos de 20 líneas y realiza exactamente una sola tarea?
* [ ] ¿Todos los nombres de variables y funciones revelan su intención y usan la convención correcta?
* [ ] ¿Tiene anotaciones de tipo (*Type Hints*) completas tanto en parámetros como en el retorno?
* [ ] ¿Las funciones privadas empiezan por guion bajo (`_`) y se ubican abajo de la función pública que las usa?
* [ ] ¿Se han evitado comentarios redundantes o aclaratorios reescribiendo el código para ser autoexplicativo?
* [ ] ¿He evitado retornar o propagar valores nulos (`None`) o códigos numéricos de error?

---

## Anexo Técnico: El Estándar de Capitalización en Código

En el desarrollo de software moderno, *Sentence case* **NO** es un estándar aplicable a la sintaxis del código fuente, sino un patrón exclusivo para interfaces de usuario y documentación de texto plano.

A continuación se detalla la taxonomía exacta de capitalización obligatoria en nuestro ecosistema:

| Estilo / Caso | Regla de Sintaxis | Aplicación en INES |
| --- | --- | --- |
| **`snake_case`** | Todo en minúsculas, palabras separadas por guiones bajos (`_`). | Variables, funciones, métodos, atributos y nombres de archivos de Python (Estándar PEP 8). |
| **`PascalCase`** *(UpperCamelCase)* | Cada palabra inicia con mayúscula, sin espacios ni separadores. | Nombres de Clases en Python, Interfaces y Componentes de Frontend (ej. React / Vue). |
| **`camelCase`** *(lowerCamelCase)* | Inicia en minúscula, las siguientes palabras inician en mayúscula. | Variables y funciones nativas del Frontend (JavaScript / TypeScript). **Prohibido en Python**. |
| **`UPPERCASE_SNAKE`** | Todo en mayúsculas, palabras separadas por guiones bajos. | Constantes globales del sistema y variables de entorno fijas (ej. `THRESHOLD_TEMP_CRITICAL`). |
| **`Sentence case`** | Solo la primera letra de la primera palabra va en mayúscula. Como una frase regular. | **Exclusivo para textos legibles por el usuario:** Títulos de documentación, mensajes de alertas (UI), textos de etiquetas (*labels*), cadenas traducidas de Django (`gettext`) o mensajes de excepciones del cliente. *Nunca en variables o funciones*. |

### ¿Por qué no se usa Sentence case en variables o funciones?

1. **Incompatibilidad sintáctica:** Los lenguajes de programación utilizan los espacios en blanco como delimitadores de instrucciones (*tokens*). Escribir `def procesar conciliacion()` genera de inmediato un error de compilación/interpretación (`SyntaxError`).
2. **Estandarización de la comunidad:** Python se rige estrictamente por la propuesta de mejora PEP 8, la cual adoptamos al 100% mediante formateadores automáticos. Romper el ecosistema con capitalizaciones ajenas degrada la capacidad de las herramientas de análisis estático y de las IAs para interpretar el código con velocidad.

> **Directriz de Diseño UI/UX e i18n:** Toda cadena en *Sentence case* destinada a la visualización del cliente final en el producto (Frontend) o generada desde los validadores del Backend debe ser redactada en español neutro de forma nativa o etiquetada con el marcador de traducción de Django `_("Texto")`. Esto garantiza que las IAs mantengan el código limpio y estandarizado en inglés sin alterar la accesibilidad idiomática de los beneficiaros y administradores de INES.

# 🚨 INDICACIONES IMPORTANTES PARA LA DEFENSA DE TESIS 🚨

Este documento contiene instrucciones rápidas sobre cómo configurar las fallas y las alertas por correo para tu demostración en vivo ante los profesores.

---

## 1. Probabilidad de Fallas Aleatorias (Simulador)

Para evitar interrupciones y que el sistema se vea estable durante tu explicación, la probabilidad de fallas aleatorias se ha reducido al **0.2%** (casi no ocurrirán solas).

Si durante la ronda de preguntas o demostración los profesores quieren ver cómo ocurren las fallas aleatorias automáticamente, debes hacer lo siguiente:

1. Abre el archivo [app27.py](file:///c:/Users/manti/OneDrive/Escritorio/TesisFinal/app27.py).
2. Ubica las siguientes líneas de código (aproximadamente en las líneas 648 y 675):
   * **Bomba:**
     ```python
     if "pump" not in protection_ends and pump_on and random.random() < 0.002:
     ```
   * **Ascensor:**
     ```python
     if "elevator" not in protection_ends and elevator_on and random.random() < 0.002:
     ```
3. Cambia el valor `0.002` (0.2%) por un valor más alto. Por ejemplo:
   * **`0.02`** (2% de probabilidad, ocurre cada ~2 minutos).
   * **`0.10`** (10% de probabilidad, ocurre casi de inmediato).
4. Guarda el archivo y reinicia el servidor (`app27.py`).

> [!TIP]
> Recuerda que también puedes inyectar fallas de forma inmediata usando el **"Control manual de sensores"** desde el propio panel de la web sin necesidad de editar código.

---

## 2. Cooldown Antiespam del Servidor de Correo

Para evitar que tu correo reciba 20 correos por minuto mientras haces pruebas, se implementó un **tiempo de espera (cooldown) de 5 minutos (300 segundos)** entre alertas automáticas por correo.

Si quieres que las alertas automáticas por correo se envíen **sin ninguna restricción de tiempo** frente a los profesores:

1. Abre el archivo [app27.py](file:///c:/Users/manti/OneDrive/Escritorio/TesisFinal/app27.py).
2. Busca la línea (aproximadamente línea 600) que dice:
   ```python
   if now - last_email_sent_time > 300:  # 5 minutes cooldown
   ```
3. Cambia el valor **`300`** por **`0`** (sin tiempo de espera) o por **`10`** (10 segundos de espera).
4. Guarda el archivo y reinicia el servidor.

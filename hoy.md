## Resumen ejecutivo

### 1. Correos y eliminación de Whatsapp:

- Se eliminó por completo la integración de WhatsApp/Twilio de app27.py (función, credenciales y hilo de ejecución).
- Se corrigió el .env con los nombres de variables correctos (SMTP_SERVER, SMTP_USER, etc.) y se añadió un lector automático de .env en app27.py para que cargue las credenciales sin librerías externas.
- Se implementó el envío de correos con PDF adjunto: send_email_alert ahora acepta un archivo PDF opcional, y la ruta /test_alert genera y envía automáticamente el reporte del edificio (última hora) en lugar del mensaje de prueba genérico.

### 2. Estabilización de Base de Datos y Backend:

- Se añadió AUTO_INCREMENT a las llaves primarias (id_usuario, id_persona, id_edificio, etc.). Esto permite registrar múltiples registros consecutivamente sin errores de base de datos de claves duplicadas.
middleware.py
- Se eliminó el bloque de código Session.objects.all().delete() al inicio de AuthMiddleware. Ahora el servidor de desarrollo puede recargarse sin desconectar al expositor.
views.py
- Se implementó la descarga de PDF real para los beneficiarios. Utiliza fpdf con un diseño limpio (cabeceras elegantes, color cian, y línea divisoria) y ofrece un fallback automático a CSV si la biblioteca no está en el entorno local.

**Se aplicó** un re-skinning completo del sistema web INES bajo una dirección de diseño *Swiss Typographic Grid* (cuadrícula tipográfica estricta, paleta monocromática negro/blanco/gris y sin decoración innecesaria). **Se mantuvo** intacta la lógica, las rutas y la estructura del backend; todo el trabajo **se enfocó** exclusivamente en la presentación visual y la organización de los estilos.

## 3. Sistema de diseño centralizado

### `design-tokens.css`

* **Se creó** este nuevo archivo para centralizar todas las variables CSS del sistema, incluyendo la paleta de colores, el espaciado, la tipografía, las transiciones y los radios.
* **Se definieron** las variables de estado funcional (ok, warn, critical) para usarse con moderación, limitándolas solo a los semáforos de datos.
* **Se integró** la tipografía *DM Sans* (Google Fonts) para reemplazar las fuentes por defecto del navegador.
* **Se estableció** una paleta basada en el negro `#0a0a0a`, el blanco `#ffffff` y una escala de grises, eliminando por completo los colores corporativos saturados.

---

## 4. Hojas de estilo globales refactorizadas

### `sidebar.css`

* **Se rediseñó** por completo el sidebar, sustituyendo las sombras por un borde derecho de 1px.
* **Se eliminó** el relleno de los links y **se implementó** un `border-left` negro para indicar la página activa.
* **Se transformó** el header tipográfico para mostrar el logotipo "INES" en mayúsculas estrictas.
* **Se migró** el badge de notificaciones desde una posición absoluta (que flotaba sobre el ícono) hacia un flujo flex, ubicándolo a la derecha del texto "Notificaciones" con un `margin-left: auto`. **Se aplicó** un diseño cuadrado (`border-radius: 0`) sin sombras, utilizando la variable `--state-critical`.

### `navbar.css`

* **Se refactorizó** la barra de navegación superior para adaptarla a la nueva línea visual.

### `perfil.css`

* **Se añadió** la regla contextual `.main-content .perfil-page` para eliminar el `padding-top: 0` que estaba hardcodeado en todos los templates.
* **Se trasladó** la clase `.config-card` desde el bloque `<style>` inline de `configuracion.html` hacia este archivo.
* **Se creó** la clase `.form-hint` para estandarizar los textos de ayuda en los formularios.

### `lista_beneficiarios.css`

* **Se agregaron** clases utilitarias al final del archivo para reemplazar los estilos inline que estaban dispersos:
* `.reportes-card--sm / --md / --lg` para controlar los anchos máximos según el contexto.
* `.report-header-title-row` para manejar la fila flex del título y el badge en las cabeceras.
* `.monitor-status` para el contenedor del estado del backend en monitoreo y notificaciones.
* `.chart-grid` para implementar el sistema de rejilla en las gráficas del panel de monitoreo.
* `.credentials-box p` para normalizar los márgenes de los párrafos.
* `.edificio-info-box span` para estilar el texto secundario en la información de los edificios.



### `login.css`

* **Se refactorizó** la pantalla de inicio de sesión para alinearla con la estética minimalista.

### `menu.css`

* **Se rediseñó** el menú de selección de rol bajo los mismos parámetros visuales.

---

## 5. Templates Django limpiados (inline styles eliminados)

**Se eliminaron** todos los atributos `style="..."` directamente en el HTML y **se reemplazaron** por clases CSS estructuradas. En total, **se intervinieron** 10 templates:

| Template | Cambios realizados |
| --- | --- |
| `usuario.html` | **Se quitaron** el `padding-top`, los márgenes de `.credentials-box` y los colores de `.edificio-info-box`. |
| `configuracion.html` | **Se eliminó** el bloque `<style>` local completo, el `padding-top` y el estilo inline del hint de contraseña. |
| `notificaciones.html` | **Se removieron** el `max-width`, el flex del título con el badge y 7 propiedades de estilo en el div del estado del backend. |
| `monitoreo.html` | **Se limpiaron** el `max-width`, el estado del backend, el grid de las gráficas y varias clases de Tailwind residuales (`bg-white rounded-xl shadow p-5 mb-6`). |
| `lista_usuario.html` | **Se suprimió** el `padding-top: 0` manual. |
| `lista_edificios.html` | **Se eliminó** el `padding-top: 0` de la estructura. |
| `registro_edificio.html` | **Se retiró** el `padding-top: 0` del contenedor. |
| `seleccionar_edificio.html` | **Se corrigió** el espaciado quitando el `padding-top: 0`. |
| `seleccionar_usuario.html` | **Se removió** el remanente de `padding-top: 0`. |
| `monitoreo_admin.html` | **Se descartó** un bloque `<style>` local completo que redefinía `body`, `.main-layout` y `.main-content`, el cual rompía la estructura del sidebar. |

---

## 6. Panel Flask (`app27.py`) — HTML embebido re-diseñado

**Se intervino** el archivo `app27.py` que aloja un servidor Flask independiente con un `HTML_TEMPLATE` de aproximadamente 440 líneas embebido como string de Python. Este componente utilizaba Tailwind CDN y un diseño completamente ajeno a la aplicación principal.

* **Se eliminó** la etiqueta `<script src="https://cdn.tailwindcss.com">` junto con todas las clases nativas de Tailwind.
* **Se integró** un bloque de CSS interno configurado con los mismos design tokens del sistema Django (mismas variables, espaciados idénticos y la tipografía *DM Sans*).
* **Se modificaron** los gráficos para pasar de barras con colores vibrantes a líneas sutiles en escala de grises (`#0a0a0a`, `#5f5f5f`, `#b0b0b0`).
* **Se transformaron** las cards de los sensores, reemplazando los estilos `rounded-xl shadow border-l-8 text-blue-600` por la clase `.sensor-card` con un `border-left: 3px solid` acoplado al semáforo de datos.
* **Se rediseñaron** los badges de riesgo, cambiando los fondos sólidos saturados por un formato tipográfico con borde y un fondo suave.
* **Se cambiaron** los botones para que lucieran cuadrados, con texto negro sobre fondo blanco.
* **Se reformuló** el estado del sistema, sustituyendo los 3 divs independientes por una cuadrícula `.status-grid` con celdas separadas por 1px.
* **Se removió** el canal de **WhatsApp** del panel de suscriptores al confirmar que no era funcional en el backend.
* **Se renombró** el título principal de "PCLogo - Monitoreo Avanzado" a "INES — Panel de Monitoreo".

---

## 7. Sidebar — badge de notificaciones corregido

* **Se identificó** un problema en el badge contador de notificaciones, el cual usaba `position: absolute` respecto al ícono de la campana, provocando que flotara de forma desalineada con coordenadas fijas (`top: -5px; right: -9px`) y sin coherencia con el texto.
* **Se reubicó** el `<span>` del badge para que se posicione **después del texto** "Notificaciones" dentro del flujo de la etiqueta `<a>`.
* **Se aprovechó** que `.sidebar-link` ya cuenta con `display: flex; align-items: center` para que el badge se alinee verticalmente de manera automática.
* **Se aplicó** un `margin-left: auto` para empujar el componente hacia el extremo derecho del link.
* **Se ajustó** su estética para que fuera totalmente cuadrada (`border-radius: 0`), sin sombras y vinculada a `var(--state-critical)`.
* **Se eliminó** la clase `.sidebar-link-icon` al quedar obsoleta y **se saneó** por completo el archivo `sidebar.css`.
* **Se verificó** la función JavaScript `setNotificationBadge()` en `live_monitoring.js`, comprobando que sigue utilizando `style.display = 'inline-flex'` y que funciona correctamente sin necesidad de cambios.
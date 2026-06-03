# RESUMEN DE CAMBIOS Y MEJORAS EN EL SISTEMA INES

### (01-06-2026)

### SE ELIMINÓ WHATSAPP Y SE CONFIGURÓ EL ENVÍO AUTOMÁTICO DE REPORTES POR CORREO ELECTRÓNICO
* Se retiró la función inactiva de WhatsApp y se configuró el sistema para que envíe de forma automática un correo electrónico con el reporte del edificio (en formato PDF adjunto) cada vez que ocurre un evento de prueba o alerta.

### SE ASEGURÓ EL REGISTRO DE NUEVOS USUARIOS Y EDIFICIOS SIN ERRORES
* Se corrigió la base de datos para que asigne automáticamente números de identificación únicos a cada nuevo registro (usuarios, edificios, personas, etc.). Esto evita bloqueos o errores de datos duplicados al ingresar información de forma consecutiva.

### SE CORRIGIÓ EL INICIO DE SESIÓN PARA EVITAR DESCONEXIONES MOLESTAS
* Se solucionó un problema que cerraba la sesión del usuario o expositor automáticamente cada vez que el servidor realizaba una actualización interna o se reiniciaba.

### SE IMPLEMENTÓ LA DESCARGA DIRECTA DE REPORTES EN PDF
* Se habilitó una función para que los usuarios puedan descargar sus reportes de beneficiarios en un documento PDF limpio, ordenado y con diseño profesional listo para imprimir.

### SE APLICÓ UN NUEVO DISEÑO VISUAL PREMIUM (ESTILO SUIZO) A TODA LA WEB
* Se actualizó la apariencia estética de toda la plataforma web utilizando un estilo moderno de cuadrícula tipográfica suiza. Se implementó una paleta de colores limpia (blanco, negro y gris) y una tipografía moderna (DM Sans), eliminando colores saturados y decoraciones innecesarias para una experiencia más profesional.

### SE REDISEÑÓ EL MENÚ LATERAL (SIDEBAR) Y LA BARRA SUPERIOR
* Se rediseñó el menú de navegación izquierdo para hacerlo más limpio, eliminando sombras pesadas y ordenando los enlaces. Además, el indicador de notificaciones ahora se ubica a la derecha del texto en forma ordenada y clara.

### SE LIMPIÓ EL CÓDIGO HTML DE 10 PANTALLAS PRINCIPALES
* Se eliminaron estilos manuales desordenados del código de las vistas (como configuración, usuarios, edificios, notificaciones, monitoreo y login). Ahora la página carga de forma óptima y mantiene el mismo estilo visual en todas sus secciones.

### SE REDISEÑÓ EL PANEL DE MONITOREO DE SENSORES EN TIEMPO REAL
* Se actualizó la pantalla independiente que muestra el estado de los sensores. Se cambiaron las gráficas de barra con colores brillantes por líneas elegantes y discretas en escala de grises, y se rediseñaron las tarjetas de los sensores con bordes que indican claramente el nivel de riesgo.

### SE CORRIGIÓ EL CONTADOR DE ALERTAS Y NOTIFICACIONES
* Se reparó un error visual que hacía que el círculo de notificaciones flotara fuera de su lugar o se encimara con los iconos del menú. Ahora se alinea automáticamente con el texto de forma limpia y responsiva.

### (02-06-2026)

### SE ELIMINÓ LA URL Y EL ESTADO DEL IFRAME DE MONITOREO EN LA VISTA DE ADMINISTRADOR
* Se quitaron los campos de texto e información redundante sobre el enlace de monitoreo que se mostraban en la interfaz del administrador para evitar confusiones de uso.

### SE CORRIGIÓ EL ERROR QUE IMPEDÍA ELIMINAR EDIFICIOS
* Se implementó la eliminación en cascada de manera correcta en el sistema. Ahora, al eliminar un edificio, la plataforma borra automáticamente sus dependencias asociadas (como sensores y registros de alertas) sin arrojar errores de base de datos ni bloquear la pantalla.

### SE REEMPLAZARON LAS ALERTAS COMUNES DEL NAVEGADOR POR VENTANAS EMERGENTES PREMIUM
* Se prohibieron los avisos grises antiguos que muestra el navegador por defecto (`alert` y `confirm`). En su lugar, se diseñaron ventanas emergentes (modales) personalizadas que respetan el estilo visual de la plataforma (bordes negros gruesos, esquinas rectas y animaciones suaves) para confirmar la eliminación de usuarios o edificios y alertar de manera elegante.

### SE ESTILIZARON LOS REPORTES PDF EN COHERENCIA CON EL DISEÑO DE LA WEB
* Se rediseñó por completo el formato de descarga de reportes en PDF para alinearlo con el estilo visual de la web. Se implementó la fuente Helvetica, se aplicó la paleta de colores de riesgo oficial de la plataforma (verde, amarillo, naranja y rojo en tonos suaves) y se estructuraron las tablas y el gráfico de barras con un diseño minimalista y limpio libre de bordes innecesarios.

### SE OPTIMIZÓ EL RENDIMIENTO Y LA FRECUENCIA DEL PANEL DE MONITOREO Y ALERTAS
* Se redujo drásticamente el flujo constante de alertas espaciando el ciclo de simulación y el stream de eventos a 5 segundos. También se redujo la probabilidad de fallos aleatorios a un nivel sumamente realista (0.2%) para evitar interrupciones no deseadas durante la defensa, e implementamos un sistema de Cooldown (espera de 5 minutos) en el servidor de correo para impedir la saturación de la bandeja de entrada cuando se inyectan fallas consecutivas.

### SE ELIMINÓ TELEGRAM Y SE INTEGRÓ LA SELECCIÓN DINÁMICA DE USUARIOS POR EDIFICIO
* Se eliminaron por completo las referencias y el servicio de Telegram para dejar únicamente el envío de alertas por correo electrónico. Además, se reemplazó el formulario manual de correos por un selector dinámico de edificios que extrae en tiempo real los nombres y correos de los usuarios registrados en la base de datos de Django para el edificio seleccionado, incluyendo un nuevo botón para realizar envíos de prueba masivos de manera instantánea.

### SE CULMINÓ LA SEGUNDA PARTE DEL FRONTEND, Y SE CORRIGIERON ERRORES DE UX/UI

### SE LE DIÓ ESTILOS A LOS CORREOS (COHERENTES AL DISEÑO ACTUAL DE NUSTRO PROYECTO)

### SE TRADUJO AL ESPAÑOL TODO ELEMENTO EN INGLÉS PRESENTE EN LA UI DEL USUARIO

### SE ELIMINÓ LA LÓGICA DE CREACIÓN DE USUARIO Y CONTRASEÑA AUTOMATICA, SE CREÓ `completar_registro.html` Y CORREOS ESTANDARIZADOS PARA LA CREACIÓN DE DICHO USUARIO.

### SE REDISEÑARON LAS VALIDACIONES DE TODOS LOS FORMULARIOS (EDIFICIO, USUARIO, CONFIGURACIÓN), AHORA MUESTRA EL CAMPO ERRONEO GRACIAS A LA IMPLEMENTACIÓN DE DJANGO ERROR EN CADA INPUT

### (03-06-2026)

### SE ACTUALIZO EL SCRIPT PARA QUE LIMPIE LA BASE DE DATOS ANTES DE AGREGAR LOS DATOS DE PRUEBA.


### SE MODIFICÓ LA CONSULTA EN `api/front/views.py` PARA QUE MUESTRE SOLO LOS USUARIOS DE ROL USER.

### SE AGREGÓ COLUMA "REGISTRADO" PARA TENER EN CUENTA A LOS USUARIOS QUE FALTAN POR ACCEDER AL SISTEMA, CUANDO EL USUARIO ACCEDE AL SISTEMA SE CAMBIA A TRUE.

### SE IMPLEMENTÓ UN SISTEMA DE FILTRADO POR EDIFICIO EN `api/front/views.py` PARA QUE MUESTRE SOLO LOS USUARIOS QUE PERTENECEN AL EDIFICIO SELECCIONADO.

### SE CULMINÓ EL FRONTEND

### SE IMPLEMENTÓ UN SISTEMA DE BOTONES PARA ENCENDER, APAGAR Y REINICIAR EL SIMULADOR DE MONITOREO.
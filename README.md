¿Qué es INES?
Es un sistema web de monitoreo en tiempo real para edificios. Supervisa bombas de agua y elevadores mediante sensores simulados. Si algo se sale de los rangos normales, envía alertas por correo electrónico y puede apagar dispositivos automáticamente para protegerlos.
Flujo completo del sistema
1. Inicio del sistema
Cuando ejecutas python server.py, pasan varias cosas:
- Se carga la configuración y las credenciales de correo (Gmail).
- Se leen los edificios y equipos registrados en la base de datos.
- Por cada edificio con bomba o elevador, se crea un simulador independiente.
- Se lanza un loop de simulación en segundo plano que cada 5 segundos genera datos de sensores (como si fueran sensores reales).
- Se inicia el servidor web en http://localhost:8000.
2. Llegada al sistema — Login
El usuario abre la página y ve la pantalla de inicio de sesión. Ingresa usuario y contraseña. El sistema verifica los datos, inicia una "sesión" y lo redirige al menú principal.
3. Menú principal
Aquí el usuario ve tarjetas con opciones. Lo que ve depende de su rol:
Si es Administrador (SA/ADMIN):
- Registrar usuario, Administrar beneficiaros
- Registrar edificio, Administrar edificios
- Monitoreo global
- Alertas
- Configuración
Si es Usuario normal (US):
- Alertas (solo de sus edificios)
- Monitoreo (solo de sus edificios)
- Configuración
4. Gestión de edificios (solo admin)
El admin llena un formulario con: nombre del edificio, dirección, RIF. Marca si tiene bomba de agua y/o elevador. El sistema guarda el edificio y crea los equipos de monitoreo correspondientes. Estos equipos son los que el simulador usará después para generar datos.
5. Gestión de beneficiaros (solo admin)
El admin llena los datos de una persona: nombres, apellidos, cédula, correo, teléfono. Selecciona a qué edificio pertenece. El sistema:
- Genera automáticamente un nombre de usuario y contraseña temporal.
- Envía un correo de activación con un enlace que vence en 24 horas.
- El usuario recibe el correo, hace clic en el enlace y elige su propio usuario y contraseña.
- Así queda registrado y puede iniciar sesión.
6. El corazón del sistema — Monitoreo en vivo
Cuando el usuario entra a Monitoreo, ve un tablero en tiempo real con datos que cambian solos cada 5 segundos. Los datos llegan mediante una conexión especial (SSE) sin necesidad de recargar la página.
Para bombas de agua se ve: caudal, presión, temperatura, vibración, nivel del tanque, voltaje, corriente.
Para elevadores se ve: velocidad, carga, consumo eléctrico, posición (piso), estado de puerta, conteo de viajes.
Cada variable tiene un semáforo de riesgo:
- 🟢 Bajo — Normal
- 🟡 Medio — Cerca del límite
- 🟠 Alto — Fuera de rango
- 🔴 Crítico — Peligro, acción inmediata
7. La simulación — ¿cómo se generan los datos?
El simulador no genera números al azar. Usa modelos físicos:
Para la bomba: calcula presión según el caudal (a más caudal, menos presión). La temperatura sube con la fricción. El nivel del tanque baja cuando la bomba trabaja y sube periódicamente (simula recarga).
Para el elevador: es una máquina de estados. El elevador "vive" su propio ciclo: está quieto, abre puertas, espera pasajeros, cierra puertas, acelera, viaja entre pisos, desacelera, y vuelve a empezar. Todo con velocidades, cargas variables y direcciones cambiantes.
Además, ocasionalmente ocurren fallas aleatorias:
- La bomba puede tener: cavitación, sobrecalentamiento, descarga bloqueada, etc.
- El elevador puede tener: motor atascado, puerta bloqueada, exceso de velocidad.
- Una falla en un dispositivo puede contagiar al otro (30% de probabilidad).
8. Sistema de alertas — el guardián
En cada ciclo de simulación, el sistema revisa todas las variables contra unos umbrales configurables:
Variable	Bajo	Medio
Caudal	≤20	≤35
Presión	≤5	≤7
Temperatura	≤70	≤85
Vibración	≤4	≤7
Nivel tanque	≥30%	≥15%
Cuando una variable llega a "Alto" o "Crítico":
1. Se registra una notificación en la base de datos.
2. Se activa la protección automática: el dispositivo (bomba o elevador) se apaga forzadamente durante 30 segundos para evitar daños.
3. Se envía un correo electrónico a todos los beneficiarios del edificio afectado (con detalles del evento y medidas correctivas).
4. Los correos se envían como máximo cada 5 minutos para no saturar.
5. Cuando termina la protección, se restaura el dispositivo a valores normales.
9. Historial de eventos
El usuario puede ver todas las notificaciones ocurridas, con filtros por:
- Edificio, severidad (Info/Bajo/Medio/Alto/Crítico), variable específica
- Periodo de tiempo: última hora, 12h, 24h, 3 días, 7 días o fechas personalizadas
- Puede descargar el historial como PDF con colores y leyenda.
10. Página de alertas activas
Similar al historial pero filtra solo lo importante (Alto y Crítico). Aquí el usuario puede:
- Silenciar alertas temporalmente (por ejemplo, 30 minutos, 1 hora, etc.)
- Limpiar/descartar alertas ya revisadas
11. Reportes PDF
Se pueden descargar dos tipos:
- Historial de eventos: PDF profesional con encabezado, leyenda de colores, tabla de eventos y medidas correctivas.
- Lista de beneficiarios: PDF con cédula, nombre, email y edificio (o CSV si falla).
12. Configuración de perfil
Cualquier usuario puede cambiar su correo, nombre de usuario y contraseña.
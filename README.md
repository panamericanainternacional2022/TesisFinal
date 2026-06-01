# TesisFinal

## Descripción

Proyecto Django para gestionar beneficiarios y edificios conectado a una base de datos MySQL.

## Requisitos

- Windows 10/11 o sistema compatible
- Python 3.13
- MySQL 8.0 o compatible
- `mysqlclient` para Django

## Dependencias principales

Estas son las versiones usadas en el proyecto:

- Django 6.0.5
- djangorestframework 3.17.1
- mysqlclient 2.2.8
- asgiref 3.11.1
- sqlparse 0.5.5
- tzdata 2026.2

## Estructura general

- `api/` - carpeta del proyecto Django
  - `manage.py` - comando para administrar el proyecto
  - `api/` - configuración principal de Django
  - `core/` - modelos y lógica del schema
  - `front/` - vistas, URLs, templates y archivos estáticos
  - `sql_tesis.sql` - esquema de base de datos MySQL a importar

- `front/templates/pages/` - plantillas HTML
- `front/static/` - estilos CSS y recursos estáticos

## Configuración de la base de datos

1. Crear la base de datos MySQL, por ejemplo `tesis`.
2. Importar `sql_tesis.sql` en MySQL.
3. Ajustar las credenciales en `api/api/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'tesis',
        'USER': 'root',
        'PASSWORD': '7316314',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}
```

> Si se traslada el proyecto a otro equipo, cambie `NAME`, `USER`, `PASSWORD`, `HOST` y `PORT` según la nueva configuración MySQL.

## Crear y activar el entorno virtual

Desde `c:\Tesis\api`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install django==6.0.5 djangorestframework==3.17.1 mysqlclient==2.2.8
```

## Instalar dependencias (alternativa)

Si se desea usar `pip freeze`, crear un archivo `requirements.txt` y luego:

```powershell
python -m pip install -r requirements.txt
```

## Ejecutar el proyecto

Desde `c:\Tesis\api` con el entorno virtual activado:

```powershell
python manage.py check
python manage.py runserver
```

Luego abrir en el navegador:

```
http://127.0.0.1:8000/login/
```

## Rutas principales de la aplicación

- `/login/` - login de acceso
- `/menu_seleccion/` - menú principal
- `/usuario/` - formulario de registro de usuario
- `/lista_usuario/` - lista de beneficiarios
- `/registro_beneficiario/` - acción de registro de usuario
- `/registro_edificio/` - formulario de registro de edificio
- `/lista_edificios/` - lista de edificios
- `/editar_beneficiario/<id>/` - editar beneficiario
- `/editar_edificio/<id>/` - editar edificio
- `/eliminar_beneficiario/<id>/` - eliminar beneficiario
- `/eliminar_edificio/<id>/` - eliminar edificio

## Notas importantes

- El proyecto actual usa MySQL; `db.sqlite3` ya no es necesario y fue eliminado.
- Las vistas y gestión de usuarios no usan el modelo `User` estándar de Django, sino un modelo `Usuario` propio.
- Para mover el proyecto a otro ordenador, copie el directorio completo, reinstale dependencias y configure `api/api/settings.py` con la nueva base de datos.

## Recomendación

Si desea seguir el estándar Django completo, se recomienda en el futuro usar un modelo de usuario basado en `AbstractUser` y un `requirements.txt` con todas las dependencias del proyecto.

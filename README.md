# adecoagro

Sistema web liviano de reportes de problemas para la fabrica `Esteril 2`.

## Stack elegido

- `Flask` para la app web
- `SQLite` como base de datos local
- `Flask-SQLAlchemy` para persistencia
- `Flask-Login` para autenticacion

Este enfoque es simple, barato y de muy bajo consumo. No requiere servidores complejos ni servicios pagos para empezar.

## Funcionalidades incluidas

- Inicio de sesion con usuarios y roles
- Usuario `admin` con acceso a todos los reportes
- Creacion de reportes con:
  - titulo
  - descripcion
  - acciones tomadas
  - repuestos usados
  - tiempo aproximado de parada
  - categoria
  - seleccion de maquina
  - adjuntos de imagenes
- Estados del reporte:
  - `Nuevo`
  - `En revision`
  - `Aprobado`
  - `Leido por el supervisor`
  - `Resuelto`
- Administracion de:
  - lineas de produccion
  - maquinas
  - categorias
  - usuarios

## Datos iniciales

- Fabrica: `Esteril 2`
- Lineas: `Linea A` y `Linea C`
- Maquinas de ejemplo en ambas lineas

## Usuarios iniciales

- `admin` / `admin123`
- `supervisor` / `supervisor123`
- `operador` / `operador123`

## Como ejecutar

1. Crear entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Iniciar el sistema:

```bash
python run.py
```

4. Abrir en el navegador:

```text
http://127.0.0.1:5000
```

## Publicarlo online gratis con Railway

La app quedo preparada para desplegarse en `Railway` con el archivo [railway.toml](/Users/emiliodelvilano/Desktop/adecoagro/railway.toml).

Puntos importantes:

- Railway permite desplegar desde GitHub
- Esta app usa `SQLite` e imagenes locales, asi que necesita almacenamiento persistente
- Railway soporta `Volumes` y en planes `Free` ofrece hasta `0.5GB` por proyecto
- Cuando attaches un volumen, Railway expone automaticamente `RAILWAY_VOLUME_MOUNT_PATH`
- La app ya usa esa variable automaticamente para guardar base e imagenes dentro del volumen

Pasos:

1. Entra a Railway y crea un proyecto nuevo desde GitHub.
2. Selecciona el repo `emiliog23/Adecoagro`.
3. Deja que Railway detecte el proyecto Python.
4. En el servicio, agrega un `Volume`.
5. Montalo en una ruta como `/app/data`.
6. Redeploy del servicio.

Con eso:

- la base SQLite quedara en el volumen
- las imagenes adjuntas tambien quedaran persistidas
- el start command saldra de `railway.toml`

Si luego quieres, puedes definir manualmente `DATA_DIR`, pero para Railway no hace falta si el volumen esta adjunto.

## Estructura

- `run.py`: punto de entrada
- `app/models.py`: modelos y seed inicial
- `app/routes.py`: rutas y logica principal
- `app/templates/`: vistas HTML
- `app/static/uploads/`: imagenes adjuntas

## Siguientes mejoras opcionales

- Historial de comentarios por reporte
- Busqueda avanzada por fecha, usuario o categoria
- Exportacion a PDF o Excel
- Carga de prioridades y criticidad

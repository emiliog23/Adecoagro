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

## Publicarlo online

La app quedo preparada para desplegarse en `Render` con el archivo [render.yaml](/Users/emiliodelvilano/Desktop/adecoagro/render.yaml).

Puntos importantes:

- Render sigue ofreciendo web services publicos con subdominio `onrender.com`
- Esta app usa `SQLite` e imagenes locales, asi que necesita almacenamiento persistente para no perder datos
- En Render eso se resuelve con un `disk`, ya dejado configurado en `render.yaml`

Pasos:

1. Subir este proyecto a un repositorio de GitHub.
2. Crear una cuenta en Render y conectar ese repositorio.
3. Crear el servicio usando el `Blueprint` o importando el repo.
4. Confirmar el despliegue y esperar la URL publica.

Si quieres durabilidad real de datos en produccion, conviene mantener el disco persistente o luego migrar a Postgres y un storage externo para imagenes.

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

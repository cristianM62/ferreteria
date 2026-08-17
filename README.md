# FerreSoft

Primera versión operativa para una ferretería única: productos, stock, ventas por ventanilla, pagos, remitos internos, anulación de tickets y resumen de ventas.

## Ejecutar

En PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

Abrir `http://127.0.0.1:5000`.

Usuarios iniciales (cambiarlos antes de producción):

- `dueno` / `Cambiar123!`
- `empleado` / `Empleado123!`

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Operación programada

La instalación incluye dos scripts listos para registrar con el Programador de tareas de Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\daily_backup.py
.\.venv\Scripts\python.exe .\scripts\monthly_sales_summary.py
```

El primero crea una copia diaria en `backups\`; el segundo deja el resumen mensual en `instance\resumenes\`. Para el despliegue con MySQL se debe configurar un backup consistente del servidor de base de datos y almacenamiento externo.

## Producción

La configuración local usa SQLite para facilitar el inicio. Para MySQL, definir `DATABASE_URL` usando un controlador MySQL compatible y ejecutar migraciones antes de producción. También debe configurarse una `SECRET_KEY` real, HTTPS, rate limiting, CSRF y el backup programado por el servidor.

Los remitos emitidos por esta versión son internos y no reemplazan comprobantes fiscales.

"""Copia local de seguridad para la instalación SQLite de FerreSoft.

Programar una vez al día mediante el Programador de tareas de Windows.
Para MySQL en producción, reemplazar esta tarea por un backup consistente
con mysqldump o con el servicio administrado elegido.
"""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "instance" / "ferresoft.db"
DESTINATION = ROOT / "backups"

if not SOURCE.exists():
    raise SystemExit(f"No se encontró la base de datos: {SOURCE}")

DESTINATION.mkdir(exist_ok=True)
target = DESTINATION / f"ferresoft-{datetime.now():%Y-%m-%d}.db"
shutil.copy2(SOURCE, target)
print(f"Backup creado: {target}")

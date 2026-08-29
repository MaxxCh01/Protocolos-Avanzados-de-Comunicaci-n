"""
Gestor de datos TLE.

Intenta descargar los TLE actuales desde CelesTrak. Si no hay conexión a
internet (o la petición falla/tarda demasiado), usa el último archivo TLE
que se haya guardado en caché para que el HMI siga pudiendo calcular
órbitas con SGP4 aunque el Raspberry Pi esté sin red.
"""
import os
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from skyfield.api import load
import config


class GestorTLE:
    def __init__(self, url=config.URL_TLE, ruta_cache=config.RUTA_CACHE_TLE):
        self.url = url
        self.ruta_cache = ruta_cache
        self.origen_datos = None   # "red", "cache" o "sin_datos"
        self.fecha_datos = None

        os.makedirs(os.path.dirname(self.ruta_cache), exist_ok=True)

    def _descargar_de_red(self):
        if requests is None:
            return None
        try:
            resp = requests.get(self.url, timeout=config.TIEMPO_TIMEOUT_RED)
            resp.raise_for_status()
            if len(resp.text.strip()) == 0:
                return None
            return resp.text
        except Exception as e:
            print(f"[TLE] Sin conexión o error de red ({e}). Se usará la caché local.")
            return None

    def _guardar_cache(self, texto):
        with open(self.ruta_cache, "w") as f:
            f.write(texto)

    def obtener_satelites(self):
        """
        Devuelve (diccionario nombre->satelite, origen_datos, fecha_del_archivo).
        Lanza RuntimeError solo si no hay red NI archivo en caché (primer uso sin internet).
        """
        texto_nuevo = self._descargar_de_red()

        if texto_nuevo:
            self._guardar_cache(texto_nuevo)
            self.origen_datos = "red"
        else:
            if not os.path.exists(self.ruta_cache):
                self.origen_datos = "sin_datos"
                raise RuntimeError(
                    "No hay conexión a internet y todavía no existe un archivo TLE en caché "
                    f"({self.ruta_cache}). Conecta el Raspberry Pi a internet al menos una vez."
                )
            self.origen_datos = "cache"

        self.fecha_datos = datetime.fromtimestamp(os.path.getmtime(self.ruta_cache))

        satelites = load.tle_file(self.ruta_cache)
        por_nombre = {sat.name: sat for sat in satelites}
        return por_nombre, self.origen_datos, self.fecha_datos

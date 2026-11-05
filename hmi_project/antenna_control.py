"""
Control de la antena.

- Calcula azimut/elevación/velocidad radial/pase del satélite respecto al
  observador usando Skyfield (SGP4 sobre los TLE). Esto lo sigue haciendo
  la Raspberry Pi, que tiene más capacidad de cómputo.
- El movimiento físico (motor de pasos de azimut + servo de elevación) y
  la lectura del módulo GPS ya NO se hacen con RPi.GPIO: se delegan a un
  Raspberry Pi Pico 2 dedicado, controlado por serial/UART a través de
  pico_link.EnlacePico. Esto evita por completo los problemas de RPi.GPIO
  en Raspberry Pi 5 (chip RP1), porque la Pi ya no toca GPIO para esto.
"""
import numpy as np
from skyfield.api import wgs84

from pico_link import EnlacePico


class ControlAntena:
    def __init__(self, observador, enlace_pico=None):
        """observador: objeto skyfield.wgs84.latlon(...) con la posición de la antena.
        enlace_pico: instancia de EnlacePico ya creada (opcional; si no se
        pasa, se crea una nueva usando la configuración de config.py)."""
        self.observador = observador
        self.enlace_pico = enlace_pico or EnlacePico()

    # ---------- Cálculo orbital (SGP4 vía Skyfield) ----------
    def calcular_az_el(self, satelite, tiempo):
        """Devuelve (azimut_grados, elevacion_grados, distancia_km) para un instante dado."""
        diferencia = satelite - self.observador
        topocentrico = diferencia.at(tiempo)
        elevacion, azimut, distancia = topocentrico.altaz()
        return azimut.degrees, elevacion.degrees, distancia.km

    def calcular_velocidad_radial(self, satelite, tiempo):
        """Velocidad radial del satélite respecto al observador, en km/s.
        Positiva = se está alejando (la frecuencia recibida baja por Doppler);
        negativa = se está acercando (la frecuencia recibida sube)."""
        diferencia = satelite - self.observador
        topocentrico = diferencia.at(tiempo)
        posicion = topocentrico.position.km
        velocidad = topocentrico.velocity.km_per_s
        distancia = float(np.linalg.norm(posicion))
        if distancia == 0:
            return 0.0
        vector_unitario = posicion / distancia
        return float(np.dot(vector_unitario, velocidad))

    def calcular_pase(self, satelite, ts, tiempo_referencia, ventana_horas=12):
        """Calcula la trayectoria (az/el y traza en tierra) del pase del
        satélite que está en curso en `tiempo_referencia`, o si no hay
        ninguno en curso, del siguiente pase dentro de `ventana_horas`.

        Devuelve None si no hay ningún pase (en curso o próximo) dentro de
        la ventana de tiempo indicada."""
        t1 = ts.tt_jd(tiempo_referencia.tt + ventana_horas / 24.0)
        tiempos, eventos = satelite.find_events(self.observador, tiempo_referencia, t1, altitude_degrees=0.0)

        pases = []
        aos_pendiente = None
        for t, ev in zip(tiempos, eventos):
            if ev == 0:  # AOS (adquisición de señal / salida del horizonte)
                aos_pendiente = t
            elif ev == 2:  # LOS (pérdida de señal / entrada al horizonte)
                if aos_pendiente is not None:
                    pases.append((aos_pendiente, t))
                    aos_pendiente = None
                else:
                    # El satélite ya estaba sobre el horizonte al iniciar la ventana.
                    pases.append((tiempo_referencia, t))

        pase_elegido = None
        for aos, los in pases:
            if los.tt >= tiempo_referencia.tt:
                pase_elegido = (aos, los)
                break

        if pase_elegido is None:
            return None

        aos, los = pase_elegido
        n_puntos = 60
        fracciones = np.linspace(0, 1, n_puntos + 1)
        jds = aos.tt + (los.tt - aos.tt) * fracciones
        tiempos_muestra = ts.tt_jd(jds)

        diferencia = satelite - self.observador
        topocentricos = diferencia.at(tiempos_muestra)
        elevaciones, azimuts, _ = topocentricos.altaz()

        subpuntos = wgs84.subpoint(satelite.at(tiempos_muestra))

        return {
            "aos": aos.utc_datetime(),
            "los": los.utc_datetime(),
            "azimuts": azimuts.degrees,
            "elevaciones": elevaciones.degrees,
            "latitudes": subpuntos.latitude.degrees,
            "longitudes": subpuntos.longitude.degrees,
            "elevacion_max": float(elevaciones.degrees.max()),
            "en_curso": aos.tt <= tiempo_referencia.tt <= los.tt,
        }

    def calcular_trayectoria_completa(self, satelite, ts, tiempo_referencia, n_puntos=120):
        """Traza en tierra (lat/lon) de UNA ÓRBITA COMPLETA del satélite,
        centrada en `tiempo_referencia` (mitad antes, mitad después). Esto es
        independiente de si hay o no un pase visible desde el observador:
        sirve para mostrar la trayectoria completa alrededor de la Tierra,
        con el satélite avanzando sobre ella en tiempo real.

        El periodo orbital se obtiene del propio modelo SGP4 del satélite
        (mean motion), así que sirve para cualquier órbita, no solo LEO."""
        movimiento_medio_rad_min = satelite.model.no_kozai  # rad/minuto
        periodo_min = 2 * np.pi / movimiento_medio_rad_min

        fracciones = np.linspace(-0.5, 0.5, n_puntos)
        jds = tiempo_referencia.tt + (periodo_min * fracciones) / (24 * 60)
        tiempos_muestra = ts.tt_jd(jds)

        subpuntos = wgs84.subpoint(satelite.at(tiempos_muestra))

        return {
            "latitudes": subpuntos.latitude.degrees,
            "longitudes": subpuntos.longitude.degrees,
            "periodo_min": periodo_min,
        }

    # ---------- Posición del observador desde el GPS del Pico ----------
    def actualizar_desde_gps(self):
        """Si el Pico 2 ya tiene un fix de GPS válido, actualiza la posición
        del observador con esas coordenadas (útil si la antena es portátil).
        Devuelve True si se actualizó, False si aún no hay fix."""
        gps = self.enlace_pico.obtener_ultimo_gps()
        if gps["fix"] and gps["lat"] is not None and gps["lon"] is not None:
            self.observador = wgs84.latlon(gps["lat"], gps["lon"], gps["alt"] or 0.0)
            return True
        return False

    # ---------- API pública ----------
    def apuntar_a(self, az_grados, el_grados):
        """Envía los ángulos deseados al Pico 2 por serial para que mueva
        el motor (azimut) y el servo (elevación). Ya no es una llamada
        bloqueante como antes: el Pico se mueve por su cuenta."""
        self.enlace_pico.enviar_angulos(az_grados, el_grados)

    def liberar(self):
        """Cierra el puerto serial con el Pico. Llamar al cerrar el programa."""
        self.enlace_pico.cerrar()

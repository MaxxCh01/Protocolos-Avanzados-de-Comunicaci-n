"""
Control de la antena.

- Calcula azimut/elevación del satélite respecto al observador usando
  Skyfield (que internamente usa SGP4 sobre los datos TLE).
- Mueve un motor de pasos 28BYJ-48 (vía ULN2003) para el AZIMUT.
- Mueve un servomotor para la ELEVACIÓN.

Si el código se ejecuta en una PC sin GPIO (por ejemplo para probarlo antes
de subirlo al Raspberry Pi), entra en "modo simulación" automáticamente:
no mueve hardware real pero sí calcula e imprime los ángulos.
"""
import time
import numpy as np
from skyfield.api import wgs84
import config

try:
    import RPi.GPIO as GPIO
    RASPBERRY = True
except (ImportError, RuntimeError):
    RASPBERRY = False

try:
    from gpiozero import Servo
except ImportError:
    Servo = None


# Secuencia de medio paso para el 28BYJ-48 (más torque y suavidad que paso completo)
SECUENCIA_MEDIO_PASO = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
]


class ControlAntena:
    def __init__(self, observador):
        """observador: objeto skyfield.wgs84.latlon(...) con la posición de la antena."""
        self.observador = observador
        self.paso_actual = 0
        self.angulo_azimut_actual = 0.0
        self.servo = None

        self._init_stepper()
        self._init_servo()

        if not RASPBERRY:
            print("[Antena] Modo simulación: no se detectó hardware Raspberry Pi (RPi.GPIO).")

    # ---------- Inicialización de hardware ----------
    def _init_stepper(self):
        if not RASPBERRY:
            return
        GPIO.setmode(GPIO.BCM)
        for pin in config.PINES_STEPPER:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 0)

    def _init_servo(self):
        if Servo is None or not RASPBERRY:
            return
        self.servo = Servo(config.PIN_SERVO_ELEVACION)

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

    # ---------- Motor de pasos: AZIMUT ----------
    def _mover_stepper_a_grados(self, grados_destino):
        grados_destino = grados_destino % 360
        pasos_destino = int((grados_destino / 360.0) * config.PASOS_POR_VUELTA)
        pasos_actuales = int((self.angulo_azimut_actual / 360.0) * config.PASOS_POR_VUELTA)

        diferencia_pasos = pasos_destino - pasos_actuales
        mitad_vuelta = config.PASOS_POR_VUELTA // 2
        # Tomar siempre el camino más corto (evita que la antena dé la vuelta completa)
        if diferencia_pasos > mitad_vuelta:
            diferencia_pasos -= config.PASOS_POR_VUELTA
        elif diferencia_pasos < -mitad_vuelta:
            diferencia_pasos += config.PASOS_POR_VUELTA

        direccion = 1 if diferencia_pasos >= 0 else -1

        if not RASPBERRY:
            print(f"[Antena-SIM] Azimut: {self.angulo_azimut_actual:.1f}° -> {grados_destino:.1f}°")
            self.angulo_azimut_actual = grados_destino
            return

        for _ in range(abs(diferencia_pasos)):
            self.paso_actual = (self.paso_actual + direccion) % 8
            for pin, valor in zip(config.PINES_STEPPER, SECUENCIA_MEDIO_PASO[self.paso_actual]):
                GPIO.output(pin, valor)
            time.sleep(0.0015)  # velocidad del motor; ajusta según tu 28BYJ-48

        self.angulo_azimut_actual = grados_destino

    # ---------- Servo: ELEVACIÓN ----------
    def _mover_servo_a_grados(self, grados_destino):
        grados_destino = max(config.SERVO_ANGULO_MIN, min(config.SERVO_ANGULO_MAX, grados_destino))

        if not RASPBERRY or self.servo is None:
            print(f"[Antena-SIM] Elevación -> {grados_destino:.1f}°")
            return

        # gpiozero.Servo usa un rango de -1..1 equivalente a 0°..180°
        valor = (grados_destino / 90.0) * 2 - 1
        self.servo.value = max(-1, min(1, valor))

    # ---------- API pública ----------
    def apuntar_a(self, az_grados, el_grados):
        """Mueve azimut y elevación a los ángulos indicados. Es una llamada BLOQUEANTE:
        en el HMI se ejecuta dentro de un hilo aparte para no congelar la interfaz."""
        self._mover_stepper_a_grados(az_grados)
        self._mover_servo_a_grados(el_grados)

    def liberar(self):
        """Apaga las bobinas del motor y libera los pines GPIO. Llamar al cerrar el programa."""
        if RASPBERRY:
            for pin in config.PINES_STEPPER:
                GPIO.output(pin, 0)
            GPIO.cleanup()

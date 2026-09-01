"""
Enlace serial con el Raspberry Pi Pico 2 que controla el GPS, el motor
(azimut) y el servo (elevación) de la antena.

El Pico NO calcula nada de órbitas: la Raspberry Pi calcula el azimut y la
elevación (SGP4 vía Skyfield) y solo le manda al Pico "apunta aquí"; el Pico
mueve el motor/servo y le reporta de vuelta la posición del GPS.

Protocolo (líneas de texto ASCII terminadas en '\\n'):
  Pi   -> Pico : CMD,<azimut_grados>,<elevacion_grados>
  Pico -> Pi   : GPS,<fix 0|1>,<lat>,<lon>,<alt_m>,<num_satelites>
                 ACK,<azimut_aplicado>,<elevacion_aplicada>

Si no se puede abrir el puerto serial (Pico no conectado, permisos, UART no
habilitado, etc.), cae a "modo simulación": no truena, solo imprime lo que
habría enviado — igual que el resto del proyecto se comporta sin hardware.
"""
import threading
import time

try:
    import serial
    PYSERIAL_DISPONIBLE = True
except ImportError:
    serial = None
    PYSERIAL_DISPONIBLE = False

import config


class EnlacePico:
    def __init__(self, puerto=None, baudios=None):
        self.puerto = puerto or config.PICO_PUERTO_SERIAL
        self.baudios = baudios or config.PICO_BAUDIOS
        self.ultimo_gps = {"fix": 0, "lat": None, "lon": None, "alt": None, "sats": 0}
        self._lock = threading.Lock()
        self._activo = False
        self._puerto_serial = None

        if not PYSERIAL_DISPONIBLE:
            print("[Pico] El paquete 'pyserial' no está instalado; modo simulación.")
        else:
            try:
                self._puerto_serial = serial.Serial(self.puerto, self.baudios, timeout=0.2)
                self._activo = True
            except Exception as e:
                print(f"[Pico] No se pudo abrir {self.puerto} ({e}); modo simulación.")

        if self._activo:
            hilo = threading.Thread(target=self._leer_en_segundo_plano, daemon=True)
            hilo.start()

    @property
    def conectado(self):
        return self._activo

    def enviar_angulos(self, az_grados, el_grados):
        """Manda al Pico el azimut/elevación deseados. No bloquea: el Pico
        mueve el motor/servo de forma asíncrona por su cuenta."""
        if not self._activo:
            print(f"[Pico-SIM] Az={az_grados:.1f}°  El={el_grados:.1f}°")
            return
        try:
            self._puerto_serial.write(f"CMD,{az_grados:.1f},{el_grados:.1f}\n".encode("ascii"))
        except Exception as e:
            print(f"[Pico] Error al enviar comando: {e}")

    def obtener_ultimo_gps(self):
        """Devuelve el último fix de GPS reportado por el Pico (o sin fix
        si aún no ha llegado ninguno)."""
        with self._lock:
            return dict(self.ultimo_gps)

    def _leer_en_segundo_plano(self):
        buffer = b""
        while self._activo:
            try:
                datos = self._puerto_serial.read(256)
                if datos:
                    buffer += datos
                    while b"\n" in buffer:
                        linea, buffer = buffer.split(b"\n", 1)
                        self._procesar_linea(linea.decode("ascii", "ignore").strip())
            except Exception as e:
                if self._activo:
                    print(f"[Pico] Error de lectura serial: {e}")
                    time.sleep(1)

    def _procesar_linea(self, linea):
        partes = linea.split(",")
        if not partes:
            return
        if partes[0] == "GPS" and len(partes) == 6:
            try:
                with self._lock:
                    self.ultimo_gps = {
                        "fix": int(partes[1]),
                        "lat": float(partes[2]),
                        "lon": float(partes[3]),
                        "alt": float(partes[4]),
                        "sats": int(partes[5]),
                    }
            except ValueError:
                pass
        # Las líneas ACK/PONG se ignoran por ahora (podrían usarse a futuro
        # para confirmar en pantalla que el Pico ya terminó de moverse).

    def cerrar(self):
        self._activo = False
        if self._puerto_serial:
            self._puerto_serial.close()

# main.py -- Firmware para Raspberry Pi Pico 2 (MicroPython)
#
# El Pico NO calcula nada de órbitas: solo hace lo que le manda la
# Raspberry Pi por UART1, y le reporta la posición del GPS.
#
# Conexiones:
#   Módulo GPS   -> UART0: TX(GPS)->GP1 (RX Pico), RX(GPS)->GP0 (TX Pico)
#   Raspberry Pi -> UART1: GP4 (TX Pico) -> GPIO15/RX de la Pi (pin físico 10)
#                           GP5 (RX Pico) -> GPIO14/TX de la Pi (pin físico 8)
#                           GND del Pico <-> GND de la Pi (obligatorio)
#   Motor 28BYJ-48 (driver ULN2003): IN1=GP2, IN2=GP3, IN3=GP6, IN4=GP7
#   Servo de elevación: cable de señal -> GP8
#
# Protocolo (líneas de texto ASCII terminadas en '\n'):
#   Pi   -> Pico : CMD,<azimut_grados>,<elevacion_grados>
#   Pico -> Pi   : GPS,<fix 0|1>,<lat>,<lon>,<alt_m>,<num_satelites>   (cada 1s)
#                  ACK,<azimut_aplicado>,<elevacion_aplicada>          (al terminar de moverse)

import machine
import uasyncio as asyncio

# ---------- Configuración de pines ----------
PASOS_POR_VUELTA = 4096
PINES_STEPPER = [2, 3, 6, 7]
PIN_SERVO = 8
BAUD_GPS = 9600
BAUD_PI = 115200

SECUENCIA_MEDIO_PASO = [
    [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0], [0, 1, 1, 0],
    [0, 0, 1, 0], [0, 0, 1, 1], [0, 0, 0, 1], [1, 0, 0, 1],
]

uart_gps = machine.UART(0, baudrate=BAUD_GPS, tx=machine.Pin(0), rx=machine.Pin(1))
uart_pi = machine.UART(1, baudrate=BAUD_PI, tx=machine.Pin(4), rx=machine.Pin(5))

pines_motor = [machine.Pin(p, machine.Pin.OUT) for p in PINES_STEPPER]
pwm_servo = machine.PWM(machine.Pin(PIN_SERVO))
pwm_servo.freq(50)

estado = {
    "paso_actual": 0,
    "angulo_azimut": 0.0,
    "angulo_elevacion": 0.0,
    "gps_fix": 0, "gps_lat": 0.0, "gps_lon": 0.0, "gps_alt": 0.0, "gps_sats": 0,
}


# ---------- GPS (NMEA GGA, sin librerías externas) ----------
def nmea_a_grados(valor, hemisferio):
    punto = valor.find(".")
    grados = float(valor[:punto - 2])
    minutos = float(valor[punto - 2:])
    decimal = grados + minutos / 60.0
    if hemisferio in ("S", "W"):
        decimal = -decimal
    return decimal


def procesar_linea_gps(linea):
    partes = linea.split(",")
    if len(partes) < 10 or "GGA" not in partes[0]:
        return
    try:
        fix = int(partes[6]) if partes[6] else 0
    except ValueError:
        fix = 0
    estado["gps_fix"] = fix
    if fix and partes[2] and partes[4]:
        try:
            estado["gps_lat"] = nmea_a_grados(partes[2], partes[3])
            estado["gps_lon"] = nmea_a_grados(partes[4], partes[5])
            estado["gps_alt"] = float(partes[9]) if partes[9] else 0.0
            estado["gps_sats"] = int(partes[7]) if partes[7] else 0
        except (ValueError, IndexError):
            pass


# ---------- Motor y servo ----------
def mover_servo(grados):
    grados = max(0, min(90, grados))
    # Pulso de servo típico: 500us (0°) .. 1500us (90°). Ajusta si tu servo
    # necesita el rango completo 500-2500us para 0-180°.
    us = 500 + (grados / 90.0) * 1000
    pwm_servo.duty_u16(int((us / 20000) * 65535))
    estado["angulo_elevacion"] = grados


def paso_stepper(direccion):
    estado["paso_actual"] = (estado["paso_actual"] + direccion) % 8
    for pin, valor in zip(pines_motor, SECUENCIA_MEDIO_PASO[estado["paso_actual"]]):
        pin.value(valor)


async def mover_azimut(grados_destino):
    grados_destino = grados_destino % 360
    pasos_destino = int((grados_destino / 360.0) * PASOS_POR_VUELTA)
    pasos_actuales = int((estado["angulo_azimut"] / 360.0) * PASOS_POR_VUELTA)
    diferencia = pasos_destino - pasos_actuales
    mitad = PASOS_POR_VUELTA // 2
    if diferencia > mitad:
        diferencia -= PASOS_POR_VUELTA
    elif diferencia < -mitad:
        diferencia += PASOS_POR_VUELTA
    direccion = 1 if diferencia >= 0 else -1
    for _ in range(abs(diferencia)):
        paso_stepper(direccion)
        await asyncio.sleep_ms(2)  # velocidad del motor; ajusta según tu 28BYJ-48
    estado["angulo_azimut"] = grados_destino


# ---------- Tareas asíncronas ----------
async def tarea_gps():
    buffer = b""
    while True:
        if uart_gps.any():
            buffer += uart_gps.read(uart_gps.any())
            while b"\n" in buffer:
                linea, buffer = buffer.split(b"\n", 1)
                try:
                    procesar_linea_gps(linea.decode("ascii", "ignore").strip())
                except Exception:
                    pass
        await asyncio.sleep_ms(50)


async def tarea_reporte_gps():
    while True:
        e = estado
        uart_pi.write("GPS,{},{:.6f},{:.6f},{:.1f},{}\n".format(
            e["gps_fix"], e["gps_lat"], e["gps_lon"], e["gps_alt"], e["gps_sats"]))
        await asyncio.sleep(1)


async def procesar_comando(linea):
    partes = linea.split(",")
    if not partes:
        return
    if partes[0] == "CMD" and len(partes) == 3:
        try:
            az = float(partes[1])
            el = float(partes[2])
        except ValueError:
            return
        await mover_azimut(az)
        mover_servo(el)
        uart_pi.write("ACK,{:.1f},{:.1f}\n".format(estado["angulo_azimut"], estado["angulo_elevacion"]))
    elif partes[0] == "PING":
        uart_pi.write("PONG\n")


async def tarea_comandos():
    buffer = b""
    while True:
        if uart_pi.any():
            buffer += uart_pi.read(uart_pi.any())
            while b"\n" in buffer:
                linea, buffer = buffer.split(b"\n", 1)
                await procesar_comando(linea.decode("ascii", "ignore").strip())
        await asyncio.sleep_ms(20)


async def principal():
    mover_servo(0)
    await asyncio.gather(tarea_gps(), tarea_reporte_gps(), tarea_comandos())


asyncio.run(principal())

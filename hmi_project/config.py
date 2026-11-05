# config.py

import os

# --- Pines GPIO (numeración BCM) para los 3 botones físicos ---
PIN_BOTON_ARRIBA = 5
PIN_BOTON_ENTER = 6
PIN_BOTON_ABAJO = 13

# --- Pines para el motor de pasos de AZIMUT (28BYJ-48 + driver ULN2003) ---
# NOTA: estos pines ya NO se usan en la Raspberry Pi. El motor y el servo
# ahora los controla el Raspberry Pi Pico 2 (ver pico_firmware/main.py);
# se dejan aquí solo como referencia histórica/documentación.
PINES_STEPPER = [17, 27, 22, 23]   # IN1, IN2, IN3, IN4 del ULN2003
PASOS_POR_VUELTA = 4096            # 28BYJ-48 en modo medio paso (8 pasos x 512 reducciones)

# --- Pin para el servo de ELEVACIÓN ---
# (también migrado al Pico 2; ver nota arriba)
PIN_SERVO_ELEVACION = 18           # GPIO18 soporta PWM por hardware
SERVO_ANGULO_MIN = 0
SERVO_ANGULO_MAX = 90              # la elevación de un satélite va de 0° (horizonte) a 90° (cenit)

# --- Enlace serial con el Raspberry Pi Pico 2 (GPS + motor + servo) ---
# El Pico se conecta por los pines UART de la Raspberry Pi (GPIO14/GPIO15),
# no por USB. Antes de usarlo, habilita el UART de hardware con:
#   sudo raspi-config -> Interface Options -> Serial Port
#     "¿Habilitar shell de login por serial?"      -> No
#     "¿Habilitar el puerto de hardware serial?"    -> Sí
# y verifica el dispositivo con: ls -l /dev/serial0
PICO_PUERTO_SERIAL = "/dev/ttyAMA0"
PICO_BAUDIOS = 115200

# --- Datos TLE ---
URL_TLE = "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle"
# Se calcula sobre el $HOME del usuario que ejecuta el programa (no un
# usuario fijo como "pi"), para que funcione sin importar el nombre de
# usuario del Raspberry Pi (maxchqto, pi, etc.).
RUTA_CACHE_TLE = os.path.join(os.path.expanduser("~"), "hmi_data", "tle_cache.txt")
TIEMPO_TIMEOUT_RED = 6  # segundos antes de considerar que no hay internet

# --- Ubicación de la estación terrena (antena) ---
# IMPORTANTE: cambia estos valores por la ubicación GPS real de tu antena.
LAT_OBSERVADOR = 22.7709
LON_OBSERVADOR = -102.5832
ELEV_OBSERVADOR_M = 2260

# --- Satélites Meteor-M monitoreados por el HMI ---
# 'clave'     = fragmento de texto usado para encontrar al satélite dentro
#               del archivo TLE de CelesTrak (grupo "weather"), donde
#               aparecen como "METEOR-M2 3" y "METEOR-M2 4".
# 'etiqueta'  = nombre que se muestra en la pantalla del HMI.
# 'frecuencia_lrpt_hz'    = frecuencia primaria de la transmisión LRPT (137 MHz).
# 'frecuencia_respaldo_hz' = frecuencia de respaldo que usan ambos satélites.
SATELITES = [
    {
        "clave": "METEOR-M2 3",
        "etiqueta": "METEOR-M 2-3",
        "lanzamiento": "27/06/2023",
        "anio_lanzamiento": 2023,
        "periodo_min": 101.3,
        "color": "#00e5ff",
        "frecuencia_lrpt_hz": 137_900_000,
        "frecuencia_respaldo_hz": 137_100_000,
    },
    {
        "clave": "METEOR-M2 4",
        "etiqueta": "METEOR-M 2-4",
        "lanzamiento": "29/02/2024",
        "anio_lanzamiento": 2024,
        "periodo_min": 101.3,
        "color": "#ff9900",
        "frecuencia_lrpt_hz": 137_900_000,
        "frecuencia_respaldo_hz": 137_100_000,
    },
]
# --- Parámetros del receptor SDR (RTL-SDR) para la pantalla de espectro ---
SDR_SAMPLE_RATE_HZ = 250_000        # ancho de banda capturado alrededor de la frecuencia LRPT
SDR_GANANCIA = "auto"
SDR_N_MUESTRAS = 256 * 1024           # tamaño total del bloque IQ capturado (más chico = respuesta más rápida)
SDR_TAMANO_SEGMENTO_FFT = 4096        # tamaño de cada segmento de la FFT promediada (método de Welch)
SDR_UMBRAL_SNR_DB = 8.0              # SNR mínimo sobre el piso de ruido para considerar la señal "detectada"
SDR_TOLERANCIA_DOPPLER_HZ = 6_000    # ventana de búsqueda del pico alrededor de la frecuencia esperada

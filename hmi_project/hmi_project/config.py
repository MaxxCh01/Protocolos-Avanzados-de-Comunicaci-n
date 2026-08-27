# config.py
"""Configuración central del proyecto HMI-NOAA para Raspberry Pi 4B."""

# --- Pines GPIO (numeración BCM) para los 3 botones físicos ---
PIN_BOTON_ARRIBA = 5
PIN_BOTON_ENTER = 6
PIN_BOTON_ABAJO = 13

# --- Pines para el motor de pasos de AZIMUT (28BYJ-48 + driver ULN2003) ---
PINES_STEPPER = [17, 27, 22, 23]   # IN1, IN2, IN3, IN4 del ULN2003
PASOS_POR_VUELTA = 4096            # 28BYJ-48 en modo medio paso (8 pasos x 512 reducciones)

# --- Pin para el servo de ELEVACIÓN ---
PIN_SERVO_ELEVACION = 18           # GPIO18 soporta PWM por hardware
SERVO_ANGULO_MIN = 0
SERVO_ANGULO_MAX = 90              # la elevación de un satélite va de 0° (horizonte) a 90° (cenit)

# --- Datos TLE ---
URL_TLE = "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle"
RUTA_CACHE_TLE = "/home/pi/hmi_data/tle_cache.txt"
TIEMPO_TIMEOUT_RED = 6  # segundos antes de considerar que no hay internet

# --- Ubicación de la estación terrena (antena) ---
# IMPORTANTE: cambia estos valores por la ubicación GPS real de tu antena.
LAT_OBSERVADOR = 22.7709
LON_OBSERVADOR = -102.5832
ELEV_OBSERVADOR_M = 2260

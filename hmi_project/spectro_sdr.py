"""
Módulo de análisis de espectro para la pantalla "Espectro SDR" del HMI.

Intenta usar un receptor RTL-SDR real (vía pyrtlsdr) para capturar el
espectro alrededor de la frecuencia LRPT (137 MHz) del satélite Meteor-M
seleccionado y detectar si su portadora está presente.

Si no hay un RTL-SDR conectado (por ejemplo durante pruebas en una PC sin
hardware, igual que el "modo simulación" que ya usa antenna_control.py),
cae a un modo de simulación: genera una señal realista basada en si el
satélite está realmente sobre el horizonte y en su velocidad radial (para
reproducir el corrimiento Doppler), de modo que la pantalla del HMI se
pueda seguir usando para desarrollo/demostración sin hardware conectado.
"""
import numpy as np
import config

try:
    from rtlsdr import RtlSdr
    HAY_HARDWARE_SDR = True
except (ImportError, OSError):
    RtlSdr = None
    HAY_HARDWARE_SDR = False

VELOCIDAD_LUZ_KM_S = 299792.458


def _capturar_con_rtlsdr(frecuencia_central_hz):
    """Captura muestras IQ reales desde un RTL-SDR conectado."""
    sdr = RtlSdr()
    try:
        sdr.sample_rate = config.SDR_SAMPLE_RATE_HZ
        sdr.center_freq = frecuencia_central_hz
        sdr.gain = config.SDR_GANANCIA
        muestras = sdr.read_samples(config.SDR_N_MUESTRAS)
    finally:
        sdr.close()
    return muestras


def _simular_muestras(frecuencia_central_hz, frecuencia_esperada_hz, hay_pase, velocidad_radial_km_s):
    """Genera muestras IQ sintéticas para cuando no hay hardware SDR conectado.

    Si `hay_pase` es False (satélite bajo el horizonte) solo devuelve ruido,
    para que la pantalla muestre correctamente "no está pasando". Si es
    True, añade un tono con corrimiento Doppler cerca de la frecuencia LRPT,
    simulando la portadora recibida durante un pase real.
    """
    n = config.SDR_N_MUESTRAS
    fs = config.SDR_SAMPLE_RATE_HZ
    ruido = (np.random.randn(n) + 1j * np.random.randn(n)) * 0.35

    if not hay_pase:
        return ruido

    corrimiento_doppler_hz = -velocidad_radial_km_s / VELOCIDAD_LUZ_KM_S * frecuencia_esperada_hz
    f_señal = (frecuencia_esperada_hz + corrimiento_doppler_hz) - frecuencia_central_hz

    t = np.arange(n) / fs
    ruido_fase = np.cumsum(np.random.randn(n)) * 0.002  # da textura de modulación QPSK/LRPT
    señal = 1.6 * np.exp(1j * (2 * np.pi * f_señal * t + ruido_fase))
    return señal + ruido


def analizar(frecuencia_central_hz, frecuencia_esperada_hz, hay_pase=True, velocidad_radial_km_s=0.0):
    """
    Captura (o simula) el espectro alrededor de `frecuencia_central_hz` y
    busca la portadora del satélite cerca de `frecuencia_esperada_hz`.

    Devuelve un diccionario con:
      - frecuencias_hz: eje de frecuencias relativo a la frecuencia central (Hz)
      - potencia_db: potencia en dB para cada frecuencia
      - piso_ruido_db: nivel de ruido estimado
      - detectado: True si se encontró una señal por encima del umbral de SNR
      - frecuencia_pico_hz: frecuencia absoluta del pico encontrado (o None)
      - snr_db: relación señal/ruido del pico encontrado
      - modo: "hardware" (RTL-SDR real) o "simulacion"
    """
    if HAY_HARDWARE_SDR:
        try:
            muestras = _capturar_con_rtlsdr(frecuencia_central_hz)
            modo = "hardware"
        except Exception as e:
            print(f"[SDR] No se pudo usar el RTL-SDR ({e}); usando modo simulación.")
            muestras = _simular_muestras(frecuencia_central_hz, frecuencia_esperada_hz,
                                          hay_pase, velocidad_radial_km_s)
            modo = "simulacion"
    else:
        muestras = _simular_muestras(frecuencia_central_hz, frecuencia_esperada_hz,
                                      hay_pase, velocidad_radial_km_s)
        modo = "simulacion"

    # Periodograma promediado (método de Welch): se parte el bloque IQ en
    # varios segmentos, se calcula la FFT de cada uno y se promedia su
    # potencia. Esto reduce muchísimo la varianza estadística del ruido
    # frente a usar una sola FFT gigante, evitando falsos positivos por
    # picos aleatorios de ruido (y es la práctica estándar en analizadores
    # de espectro SDR reales).
    n_segmento = config.SDR_TAMANO_SEGMENTO_FFT
    n_bloques = len(muestras) // n_segmento
    bloques = muestras[: n_bloques * n_segmento].reshape(n_bloques, n_segmento)

    ventana = np.hanning(n_segmento)
    espectros = np.fft.fftshift(np.fft.fft(bloques * ventana, axis=1), axes=1)
    potencia_lineal = np.mean(np.abs(espectros) ** 2, axis=0)
    potencia_db = 10 * np.log10(potencia_lineal + 1e-12)
    frecuencias_hz = np.fft.fftshift(np.fft.fftfreq(n_segmento, d=1.0 / config.SDR_SAMPLE_RATE_HZ))

    piso_ruido_db = float(np.median(potencia_db))

    frecuencia_relativa_esperada = frecuencia_esperada_hz - frecuencia_central_hz
    mascara = np.abs(frecuencias_hz - frecuencia_relativa_esperada) <= config.SDR_TOLERANCIA_DOPPLER_HZ
    if not np.any(mascara):
        mascara = np.ones_like(frecuencias_hz, dtype=bool)

    indice_local = int(np.argmax(potencia_db[mascara]))
    potencia_pico_db = float(potencia_db[mascara][indice_local])
    frecuencia_pico_relativa = float(frecuencias_hz[mascara][indice_local])

    snr_db = potencia_pico_db - piso_ruido_db
    detectado = snr_db >= config.SDR_UMBRAL_SNR_DB

    return {
        "frecuencias_hz": frecuencias_hz,
        "potencia_db": potencia_db,
        "piso_ruido_db": piso_ruido_db,
        "detectado": bool(detectado),
        "frecuencia_pico_hz": (frecuencia_central_hz + frecuencia_pico_relativa) if detectado else None,
        "snr_db": float(snr_db),
        "modo": modo,
    }

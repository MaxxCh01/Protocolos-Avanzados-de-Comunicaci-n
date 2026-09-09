"""
Módulo de análisis de espectro para la pantalla "Espectro SDR" del HMI.

Usa un receptor RTL-SDR real (vía pyrtlsdr) para capturar el espectro
alrededor de la frecuencia LRPT (137 MHz) del satélite Meteor-M
seleccionado y detectar si su portadora está presente.

IMPORTANTE: si no hay un RTL-SDR conectado, este módulo NO inventa
ninguna señal — devuelve ruido puro y lo marca como modo "sin_hardware",
para que la pantalla del HMI muestre honestamente "SDR no conectado" en
vez de simular una portadora que no existe de verdad.
"""
import numpy as np
import config

try:
    from rtlsdr import RtlSdr
    HAY_HARDWARE_SDR = True
except (ImportError, OSError, AttributeError) as e:
    print(f"[SDR] No se pudo importar pyrtlsdr/librtlsdr: {e}")
    print("[SDR] Corre 'python3 diagnostico_sdr.py' para diagnosticar por qué.")
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


def _ruido_puro():
    """Sin hardware conectado no hay nada que capturar de verdad: se
    devuelve solo ruido, sin ninguna portadora simulada."""
    n = config.SDR_N_MUESTRAS
    return (np.random.randn(n) + 1j * np.random.randn(n)) * 0.35


def analizar(frecuencia_central_hz, frecuencia_esperada_hz, hay_pase=True, velocidad_radial_km_s=0.0):
    """
    Captura el espectro alrededor de `frecuencia_central_hz` y busca la
    portadora del satélite cerca de `frecuencia_esperada_hz`.

    Devuelve un diccionario con:
      - frecuencias_hz: eje de frecuencias relativo a la frecuencia central (Hz)
      - potencia_db: potencia en dB para cada frecuencia
      - piso_ruido_db: nivel de ruido estimado
      - detectado: True si se encontró una señal por encima del umbral de SNR
      - frecuencia_pico_hz: frecuencia absoluta del pico encontrado (o None)
      - snr_db: relación señal/ruido del pico encontrado
      - modo: "hardware" (RTL-SDR real y funcionando) o
              "sin_hardware" (no hay ningún RTL-SDR conectado; ruido puro)
    """
    if HAY_HARDWARE_SDR:
        try:
            muestras = _capturar_con_rtlsdr(frecuencia_central_hz)
            modo = "hardware"
        except Exception as e:
            print(f"[SDR] No se pudo usar el RTL-SDR ({e}).")
            muestras = _ruido_puro()
            modo = "sin_hardware"
    else:
        muestras = _ruido_puro()
        modo = "sin_hardware"

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
    # Sin hardware real nunca se declara "detectado", sin importar qué tan
    # ruidoso salga el piso: no hay portadora real que detectar.
    detectado = (modo == "hardware") and (snr_db >= config.SDR_UMBRAL_SNR_DB)

    return {
        "frecuencias_hz": frecuencias_hz,
        "potencia_db": potencia_db,
        "piso_ruido_db": piso_ruido_db,
        "detectado": bool(detectado),
        "frecuencia_pico_hz": (frecuencia_central_hz + frecuencia_pico_relativa) if detectado else None,
        "snr_db": float(snr_db),
        "modo": modo,
    }

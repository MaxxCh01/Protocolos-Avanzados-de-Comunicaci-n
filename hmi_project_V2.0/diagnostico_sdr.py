"""
Diagnóstico del RTL-SDR: revisa, en orden, las 4 causas más comunes de que
un RTL-SDR "no se detecte" en Linux/Raspberry Pi, e imprime exactamente
cuál es el problema y cómo resolverlo.

Uso (en la Raspberry Pi, con el RTL-SDR conectado por USB):
    python3 diagnostico_sdr.py
"""
import subprocess
import sys


def _titulo(txt):
    print(f"\n{'='*60}\n{txt}\n{'='*60}")


def _ejecutar(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception as e:
        return f"(no se pudo ejecutar {' '.join(cmd)}: {e})"


# ---------------------------------------------------------------------------
_titulo("1) ¿La Raspberry Pi ve el dispositivo USB?")
salida_lsusb = _ejecutar(["lsusb"])
print(salida_lsusb.strip() or "(lsusb no disponible)")

tiene_rtl = "RTL2838" in salida_lsusb or "RTL2832" in salida_lsusb or "Realtek" in salida_lsusb
if tiene_rtl:
    print("\n✅ El sistema operativo SÍ ve el dongle RTL-SDR por USB.")
else:
    print("\n❌ No aparece ningún dispositivo Realtek/RTL en 'lsusb'.")
    print("   -> Prueba con otro puerto USB, otro cable, y confirma que")
    print("      el LED del dongle enciende. Si sigue sin aparecer aquí,")
    print("      el problema es físico/USB, no de software.")
    sys.exit(0)

# ---------------------------------------------------------------------------
_titulo("2) ¿El driver de TV (DVB-T) está bloqueando el dongle?")
# Esta es LA causa más común: el kernel de Linux carga automáticamente el
# driver de sintonizador de TV digital (dvb_usb_rtl28xxu) apenas conecta el
# dongle, porque el mismo chip (RTL2832U) también se usa para ver TV. Ese
# driver "acapara" el dispositivo y no deja que librtlsdr lo abra.
salida_lsmod = _ejecutar(["lsmod"])
modulos_conflictivos = [m for m in ["dvb_usb_rtl28xxu", "rtl2832", "rtl2830"] if m in salida_lsmod]
if modulos_conflictivos:
    print(f"❌ Encontrados módulos del kernel bloqueando el dongle: {modulos_conflictivos}")
    print("   -> Solución (bloquearlos permanentemente):")
    print("      sudo tee /etc/modprobe.d/blacklist-rtlsdr.conf <<EOF")
    print("      blacklist dvb_usb_rtl28xxu")
    print("      blacklist rtl2832")
    print("      blacklist rtl2830")
    print("      EOF")
    print("      sudo rmmod dvb_usb_rtl28xxu rtl2832 rtl2830 2>/dev/null")
    print("      (o reinicia la Raspberry Pi para que el blacklist tome efecto)")
else:
    print("✅ No hay módulos del driver de TV cargados; no está bloqueando el dongle.")

# ---------------------------------------------------------------------------
_titulo("3) ¿Está instalado librtlsdr (la librería del sistema, no solo el paquete Python)?")
# pyrtlsdr es solo un "wrapper" de Python: necesita que la librería nativa
# librtlsdr esté instalada aparte con apt, si no, el import falla.
try:
    from rtlsdr import RtlSdr, librtlsdr
    print("✅ El paquete Python 'pyrtlsdr' se importa correctamente.")
    ruta_librtlsdr_ok = True
except OSError as e:
    print(f"❌ pyrtlsdr no encuentra la librería nativa librtlsdr: {e}")
    print("   -> Instálala con: sudo apt install rtl-sdr librtlsdr0 librtlsdr-dev")
    ruta_librtlsdr_ok = False
except ImportError as e:
    print(f"❌ El paquete Python 'pyrtlsdr' no está instalado: {e}")
    print("   -> Instálalo con: pip3 install pyrtlsdr --break-system-packages")
    ruta_librtlsdr_ok = False
except AttributeError as e:
    print(f"❌ Incompatibilidad de versiones entre pyrtlsdr y librtlsdr: {e}")
    print("   -> El pyrtlsdr instalado espera una función (probablemente")
    print("      rtlsdr_set_dithering) que tu librtlsdr del sistema, más vieja,")
    print("      no tiene. La solución más rápida es bajar la versión de pyrtlsdr")
    print("      a una anterior a ese cambio:")
    print("      pip3 uninstall pyrtlsdr --break-system-packages")
    print('      pip3 install "pyrtlsdr==0.2.92" --break-system-packages')
    ruta_librtlsdr_ok = False

if not ruta_librtlsdr_ok:
    sys.exit(0)

# ---------------------------------------------------------------------------
_titulo("4) ¿Se puede abrir el dispositivo (permisos USB)?")
try:
    sdr = RtlSdr()
    print("✅ ¡El RTL-SDR se abrió correctamente! El hardware funciona.")
    print(f"   Ganancias disponibles: {sdr.valid_gains_db}")
    sdr.close()
    print("\n>>> Todo en orden. Si el HMI sigue sin detectarlo, cierra por completo")
    print(">>> el HMI y vuelve a abrirlo (el módulo Python solo revisa esto una vez")
    print(">>> al iniciar el programa).")
except Exception as e:
    texto = str(e)
    print(f"❌ No se pudo abrir el dispositivo: {texto}")
    if "Permission denied" in texto or "usb_open" in texto.lower():
        print("   -> Es un problema de PERMISOS USB. Dos soluciones:")
        print("      a) Rápida (prueba): ejecuta el HMI con sudo")
        print("      b) Correcta (permanente): crea una regla udev")
        print("         sudo tee /etc/udev/rules.d/20-rtlsdr.rules <<EOF")
        print('         SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE="0666"')
        print("         EOF")
        print("         sudo udevadm control --reload-rules && sudo udevadm trigger")
        print("         (desconecta y vuelve a conectar el dongle después de esto)")
    else:
        print("   -> Revisa que ningún otro programa (SDR#, GQRX, otra instancia")
        print("      del HMI) esté usando el dongle al mismo tiempo; el RTL-SDR")
        print("      solo lo puede abrir un programa a la vez.")

"""
Lanza la vista 3D de la trayectoria (trayectoria_3d.html) en Chromium, en
modo kiosco, desde el propio HMI de Tkinter.

Tkinter no puede dibujar WebGL/Three.js directamente, así que en vez de
intentar "incrustar" el navegador dentro de la ventana de Tkinter (que en
Raspberry Pi es complicado y pesado), este módulo:

  1. Oculta la ventana de Tkinter (root.withdraw()).
  2. Abre Chromium a pantalla completa apuntando al HTML local.
  3. Cuando el usuario cierra Chromium (botón "Salir", Esc, o Alt+F4),
     este módulo lo detecta y vuelve a mostrar la ventana de Tkinter.

Todo corre sin internet: el HTML usa three.min.js y la textura de la
Tierra desde la carpeta assets/ del propio proyecto (no un CDN).
"""
import os
import shutil
import subprocess
import threading


def _ruta_navegador():
    """Busca un navegador compatible con --kiosk instalado en el sistema."""
    candidatos = ["chromium-browser", "chromium", "google-chrome", "google-chrome-stable"]
    for nombre in candidatos:
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def abrir_trayectoria_3d(root, nombre_archivo="trayectoria_3d.html", on_error=None):
    """Abre la vista 3D en Chromium y oculta la ventana de Tkinter mientras
    tanto. Cuando Chromium se cierra, vuelve a mostrar la ventana.

    root: la instancia de tk.Tk() (o Toplevel) del HMI.
    on_error: función opcional que se llama con un mensaje de texto si algo
    sale mal (por ejemplo, si Chromium no está instalado)."""
    navegador = _ruta_navegador()
    if not navegador:
        mensaje = ("No se encontró Chromium instalado. Instálalo con:\n"
                   "sudo apt install chromium-browser")
        if on_error:
            root.after(0, on_error, mensaje)
        return

    ruta_base = os.path.dirname(os.path.abspath(__file__))
    ruta_html = os.path.join(ruta_base, nombre_archivo)
    if not os.path.exists(ruta_html):
        mensaje = f"No se encontró el archivo {nombre_archivo} en {ruta_base}"
        if on_error:
            root.after(0, on_error, mensaje)
        return

    url = "file://" + ruta_html

    root.withdraw()  # oculta el HMI de Tkinter mientras se ve la vista 3D

    def _worker():
        try:
            proceso = subprocess.Popen([
                navegador,
                "--kiosk",
                "--incognito",
                "--noerrdialogs",
                "--disable-infobars",
                url,
            ])
            proceso.wait()  # se bloquea hasta que el usuario cierra Chromium
        except Exception as e:
            if on_error:
                root.after(0, on_error, f"No se pudo abrir Chromium: {e}")
        finally:
            root.after(0, root.deiconify)  # vuelve a mostrar el HMI

    hilo = threading.Thread(target=_worker, daemon=True)
    hilo.start()

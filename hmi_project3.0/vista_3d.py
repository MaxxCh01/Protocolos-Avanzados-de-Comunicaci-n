"""
Lanza la vista 3D de la trayectoria (trayectoria_3d.html) en Chromium, en
modo kiosco, desde el propio HMI de Tkinter.

Tkinter no puede dibujar WebGL/Three.js directamente, así que en vez de
intentar "incrustar" el navegador dentro de la ventana de Tkinter (que en
Raspberry Pi es complicado y pesado), este módulo:

  1. Levanta un pequeño servidor HTTP LOCAL (127.0.0.1) que sirve los
     archivos del proyecto. Esto es necesario porque Chromium bloquea por
     CORS la carga de texturas/imágenes cuando el HTML se abre directo
     como archivo (file://) — con http://127.0.0.1 no hay ese bloqueo,
     y sigue sin usar internet real: nunca sale de la propia Raspberry Pi.
  2. Oculta la ventana de Tkinter (root.withdraw()).
  3. Abre Chromium a pantalla completa apuntando a http://127.0.0.1:<puerto>/trayectoria_3d.html
  4. Cuando el usuario cierra Chromium (botón "Salir", Esc, o Alt+F4),
     este módulo lo detecta y vuelve a mostrar la ventana de Tkinter.
"""
import os
import shutil
import socket
import subprocess
import threading
import http.server
import functools

_SERVIDOR = None  # se reutiliza entre llamadas, no se relanza cada vez


def _ruta_navegador():
    """Busca un navegador compatible con --kiosk instalado en el sistema."""
    candidatos = ["chromium-browser", "chromium", "google-chrome", "google-chrome-stable"]
    for nombre in candidatos:
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def _puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _asegurar_servidor(ruta_base):
    """Levanta (una sola vez) un servidor HTTP local que sirve `ruta_base`.
    Solo escucha en 127.0.0.1, así que no es accesible desde fuera de la
    propia Raspberry Pi ni requiere internet."""
    global _SERVIDOR
    if _SERVIDOR is not None:
        return _SERVIDOR["puerto"]

    puerto = _puerto_libre()
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ruta_base)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), manejador)

    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()

    _SERVIDOR = {"httpd": httpd, "puerto": puerto}
    return puerto


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

    try:
        puerto = _asegurar_servidor(ruta_base)
    except Exception as e:
        mensaje = f"No se pudo levantar el servidor local para la vista 3D: {e}"
        if on_error:
            root.after(0, on_error, mensaje)
        return

    url = f"http://127.0.0.1:{puerto}/{nombre_archivo}"

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

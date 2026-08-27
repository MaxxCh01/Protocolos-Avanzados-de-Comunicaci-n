import threading
import tkinter as tk
from tkinter import font
from datetime import datetime

from skyfield.api import load, wgs84

import config
from tle_manager import GestorTLE
from antenna_control import ControlAntena
from gpio_buttons import BotonesFisicos


class HMISimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("HMI - Proyecto NOAA UPIIZ-IPN (Datos Reales)")

        # Pantalla completa (kiosco) para la pantalla del Raspberry Pi.
        # Presiona Esc para salir de pantalla completa mientras desarrollas en PC.
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.configure(bg="black")

        self.font_title = font.Font(family="Helvetica", size=18, weight="bold")
        self.font_normal = font.Font(family="Helvetica", size=13)

        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=6)
        self.root.columnconfigure(2, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.crear_panel_izquierdo()
        self.crear_panel_derecho()

        self.pantalla = tk.Frame(self.root, bg="white", bd=5, relief="ridge")
        self.pantalla.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.satelite_actual = ""

        # ---- Navegación con los 3 botones físicos ----
        self.widgets_menu = []
        self.indice_seleccion = 0

        # ---- Datos orbitales (TLE + SGP4 vía Skyfield) ----
        print("Cargando datos astronómicos y TLE...")
        self.ts = load.timescale()
        self.gestor_tle = GestorTLE()
        self.por_nombre = {}
        self.origen_tle = None
        self.fecha_tle = None
        self._cargar_tle()

        self.observador = wgs84.latlon(
            config.LAT_OBSERVADOR, config.LON_OBSERVADOR, config.ELEV_OBSERVADOR_M
        )
        self.control_antena = ControlAntena(self.observador)

        self.info_estatica = {
            "NOAA 15": {"lanzamiento": "13/05/1998", "anio": 1998},
            "NOAA 18": {"lanzamiento": "20/05/2005", "anio": 2005},
            "NOAA 19": {"lanzamiento": "06/02/2009", "anio": 2009},
        }

        # ---- Botones físicos GPIO (con respaldo de teclado para pruebas en PC) ----
        self.botones = BotonesFisicos(
            callback_arriba=self._on_arriba,
            callback_enter=self._on_enter,
            callback_abajo=self._on_abajo,
        )
        self.root.bind("<Up>", lambda e: self._on_arriba())
        self.root.bind("<Down>", lambda e: self._on_abajo())
        self.root.bind("<Return>", lambda e: self._on_enter())

        print("¡Datos cargados con éxito!")
        self.mostrar_inicio()

    # ==========================================
    # TLE
    # ==========================================
    def _cargar_tle(self):
        try:
            self.por_nombre, self.origen_tle, self.fecha_tle = self.gestor_tle.obtener_satelites()
            print(f"TLE cargados desde: {self.origen_tle} ({self.fecha_tle})")
        except RuntimeError as e:
            print(f"ERROR TLE: {e}")
            self.por_nombre = {}
            self.origen_tle = "sin_datos"

    def _buscar_satelite(self, nombre_satelite):
        for nombre_oficial, sat in self.por_nombre.items():
            if nombre_satelite in nombre_oficial:
                return sat
        return None

    # ==========================================
    # NAVEGACIÓN CON LOS 3 BOTONES FÍSICOS
    # ==========================================
    # Los callbacks de gpiozero llegan en un hilo aparte; por eso siempre
    # se agenda el trabajo real con root.after(0, ...) para tocar Tkinter
    # solo desde el hilo principal.
    def _on_arriba(self):
        self.root.after(0, self._mover_seleccion, -1)

    def _on_abajo(self):
        self.root.after(0, self._mover_seleccion, 1)

    def _on_enter(self):
        self.root.after(0, self._activar_seleccion)

    def _mover_seleccion(self, delta):
        if not self.widgets_menu:
            return
        self._resaltar(False)
        self.indice_seleccion = (self.indice_seleccion + delta) % len(self.widgets_menu)
        self._resaltar(True)

    def _activar_seleccion(self):
        if not self.widgets_menu:
            return
        self.widgets_menu[self.indice_seleccion].invoke()

    def _resaltar(self, activo):
        widget = self.widgets_menu[self.indice_seleccion]
        if activo:
            widget.configure(bg="#ffcc00", relief="solid", bd=3)
        else:
            widget.configure(bg=getattr(widget, "_bg_original", "#f0f0f0"), relief="groove", bd=2)

    def registrar_menu(self, widgets):
        """Cada pantalla llama esto con la lista de botones que se pueden recorrer
        con los botones físicos ARRIBA/ABAJO, en el orden en que deben resaltarse."""
        self.widgets_menu = widgets
        self.indice_seleccion = 0
        for w in widgets:
            w._bg_original = w.cget("bg")
        if widgets:
            self._resaltar(True)

    # ==========================================
    # PANELES FIJOS (paro de emergencia y botones táctiles de respaldo)
    # ==========================================
    def limpiar_pantalla(self):
        for widget in self.pantalla.winfo_children():
            widget.destroy()

    def crear_panel_izquierdo(self):
        panel = tk.Frame(self.root, bg="#e0e0e0")
        panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=10)

        btn_paro = tk.Button(panel, text="PARO DE\nEMERGENCIA", bg="#cc0000", fg="white",
                             font=self.font_title, height=4, command=self._paro_emergencia)
        btn_paro.pack(expand=True, fill="x", padx=10)

    def _paro_emergencia(self):
        self.control_antena.liberar()
        self.root.quit()

    def crear_panel_derecho(self):
        # Botones táctiles equivalentes a los físicos (útiles si la pantalla es táctil).
        panel = tk.Frame(self.root, bg="#e0e0e0")
        panel.grid(row=0, column=2, sticky="nsew", padx=5, pady=10)

        tk.Button(panel, text="↑", bg="#0055a4", fg="white", font=self.font_title, height=2,
                  command=self._on_arriba).pack(expand=True, fill="x", padx=10, pady=5)
        tk.Button(panel, text="ENTER", bg="#2ca02c", fg="white", font=self.font_title, height=2,
                  command=self._on_enter).pack(expand=True, fill="x", padx=10, pady=5)
        tk.Button(panel, text="↓", bg="#0055a4", fg="white", font=self.font_title, height=2,
                  command=self._on_abajo).pack(expand=True, fill="x", padx=10, pady=5)

    # ==========================================
    # PANTALLAS
    # ==========================================
    def mostrar_inicio(self):
        self.limpiar_pantalla()
        tk.Label(self.pantalla, text="[ Imagen Engrane UPIIZ ]          [ Imagen IPN ]",
                 bg="white", font=self.font_title, fg="#888888").pack(pady=40)

        texto_estado, color = {
            "red": ("TLE actualizados desde internet", "green"),
            "cache": (f"TLE en caché ({self.fecha_tle.strftime('%d/%m/%Y %H:%M')})"
                      if self.fecha_tle else "TLE en caché", "orange"),
            "sin_datos": ("⚠ Sin datos TLE disponibles: conecta el Raspberry a internet una vez", "red"),
        }.get(self.origen_tle, ("", "black"))
        tk.Label(self.pantalla, text=texto_estado, bg="white", font=self.font_normal, fg=color).pack()

        btn_inicio = tk.Button(self.pantalla, text="Inicio", font=self.font_normal, width=20,
                               command=self.mostrar_seleccion, relief="groove", bd=2, bg="#f0f0f0")
        btn_inicio.pack(pady=20)

        self.registrar_menu([btn_inicio])

    def mostrar_seleccion(self):
        self.limpiar_pantalla()
        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal,
                                  command=self.mostrar_inicio, bg="#f0f0f0")
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text="Seleccionar satélite", bg="white", font=self.font_title).pack(pady=25)

        botones = []
        for sat in ["NOAA 15", "NOAA 18", "NOAA 19"]:
            btn = tk.Button(self.pantalla, text=sat, font=self.font_normal, width=25, bg="#f0f0f0",
                            command=lambda s=sat: self.mostrar_info_satelite(s))
            btn.pack(pady=6)
            botones.append(btn)

        botones.append(btn_regresar)
        self.registrar_menu(botones)

    def calcular_datos_satelite(self, nombre_satelite):
        """Altitud y velocidad geocéntricas (informativas) + datos estáticos de lanzamiento."""
        satelite = self._buscar_satelite(nombre_satelite)
        if not satelite:
            print(f"Advertencia: No se encontró {nombre_satelite} en la base de datos.")
            return "N/A", "N/A", "N/A", "N/A"

        tiempo_actual = self.ts.now()
        geocentrico = satelite.at(tiempo_actual)

        subpunto = wgs84.subpoint(geocentrico)
        altitud_km = subpunto.elevation.km

        vx, vy, vz = geocentrico.velocity.km_per_s
        velocidad_km_s = (vx**2 + vy**2 + vz**2) ** 0.5

        info = self.info_estatica.get(nombre_satelite, {"lanzamiento": "Desconocido", "anio": 0})
        anios_activo = datetime.now().year - info["anio"]

        return f"{altitud_km:.2f} km", f"{velocidad_km_s:.2f} km/s", info["lanzamiento"], str(anios_activo)

    def mostrar_info_satelite(self, satelite):
        self.limpiar_pantalla()
        self.satelite_actual = satelite

        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal,
                                  command=self.mostrar_seleccion, bg="#f0f0f0")
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text=f"Satélite {satelite}", bg="white", font=self.font_title).pack(pady=15)

        frame_contenido = tk.Frame(self.pantalla, bg="white")
        frame_contenido.pack(fill="both", expand=True, padx=40, pady=10)

        altitud, velocidad, lanzamiento, anios = self.calcular_datos_satelite(satelite)

        frame_datos = tk.Frame(frame_contenido, bg="white")
        frame_datos.pack(side="left", fill="both", expand=True)
        for etiqueta, valor in [("Altitud:", altitud), ("Velocidad:", velocidad),
                                 ("Día de lanzamiento:", lanzamiento), ("Años activo:", anios)]:
            tk.Label(frame_datos, text=f"{etiqueta} {valor}", bg="white", font=self.font_normal,
                     anchor="w").pack(fill="x", pady=6)

        frame_botones = tk.Frame(frame_contenido, bg="white")
        frame_botones.pack(side="right", fill="both", expand=True)

        btn_trayectoria = tk.Button(frame_botones, text="Trayectoria", font=self.font_normal, width=18,
                                     bg="#f0f0f0", command=self.mostrar_trayectoria)
        btn_trayectoria.pack(pady=10)

        btn_espectro = tk.Button(frame_botones, text="Espectro SDR", font=self.font_normal, width=18,
                                  bg="#f0f0f0", command=self.mostrar_menu_espectro)
        btn_espectro.pack(pady=10)

        btn_apuntar = tk.Button(frame_botones, text="Apuntar antena", font=self.font_normal, width=18,
                                 bg="#f0f0f0", command=lambda: self.apuntar_antena(satelite))
        btn_apuntar.pack(pady=10)

        self.registrar_menu([btn_trayectoria, btn_espectro, btn_apuntar, btn_regresar])

    def mostrar_trayectoria(self):
        self.limpiar_pantalla()
        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                 command=lambda: self.mostrar_info_satelite(self.satelite_actual))
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text="Trayectoria", bg="white", font=self.font_title).pack(pady=10)

        frame_graficas = tk.Frame(self.pantalla, bg="white")
        frame_graficas.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(frame_graficas, text="[ Gráfica de Mapa ]\nEspacio reservado para Matplotlib",
                bg="#f0f0f0", relief="sunken").pack(side="left", fill="both", expand=True, padx=5)
        tk.Label(frame_graficas, text="[ Gráfica Polar ]\nElevación y Azimut",
                bg="#f0f0f0", relief="sunken").pack(side="right", fill="both", expand=True, padx=5)

        self.registrar_menu([btn_regresar])

    def mostrar_menu_espectro(self):
        self.limpiar_pantalla()
        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                 command=lambda: self.mostrar_info_satelite(self.satelite_actual))
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text="Espectro SDR", bg="white", font=self.font_title).pack(pady=30)

        frame_botones = tk.Frame(self.pantalla, bg="white")
        frame_botones.pack(pady=30)

        btn_con = tk.Button(frame_botones, text="Espectro con\nEfecto doppler", font=self.font_normal,
                            width=18, height=3, bg="#f0f0f0",
                            command=lambda: self.mostrar_grafica_espectro("con efecto Doppler"))
        btn_con.pack(side="left", padx=20)

        btn_sin = tk.Button(frame_botones, text="Espectro sin\nEfecto doppler", font=self.font_normal,
                            width=18, height=3, bg="#f0f0f0",
                            command=lambda: self.mostrar_grafica_espectro("sin efecto Doppler"))
        btn_sin.pack(side="right", padx=20)

        self.registrar_menu([btn_con, btn_sin, btn_regresar])

    def mostrar_grafica_espectro(self, tipo):
        self.limpiar_pantalla()
        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                  command=self.mostrar_menu_espectro)
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text=f"Espectro SDR {tipo}", bg="white", font=self.font_title).pack(pady=10)
        tk.Label(self.pantalla, text="[ Cascada FFT ]\nEspacio reservado para librería pyrtlsdr",
                bg="#001133", fg="#00ff00", font=self.font_title, relief="sunken").pack(
            fill="both", expand=True, padx=30, pady=20)

        self.registrar_menu([btn_regresar])

    # ==========================================
    # APUNTADO DE ANTENA (SGP4 + motor/servo)
    # ==========================================
    def apuntar_antena(self, nombre_satelite):
        self.limpiar_pantalla()
        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                  command=lambda: self.mostrar_info_satelite(self.satelite_actual))
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text=f"Apuntando antena a {nombre_satelite}", bg="white",
                 font=self.font_title).pack(pady=20)

        lbl_estado = tk.Label(self.pantalla, text="Calculando posición orbital...", bg="white",
                              font=self.font_normal)
        lbl_estado.pack(pady=10)

        self.registrar_menu([btn_regresar])

        # El movimiento de motores puede tardar varios segundos: se hace en un
        # hilo aparte para que la interfaz y los botones físicos sigan respondiendo.
        hilo = threading.Thread(
            target=self._apuntar_antena_worker, args=(nombre_satelite, lbl_estado), daemon=True
        )
        hilo.start()

    def _apuntar_antena_worker(self, nombre_satelite, lbl_estado):
        satelite = self._buscar_satelite(nombre_satelite)
        if not satelite:
            self.root.after(0, lambda: lbl_estado.configure(text="No se encontraron datos TLE."))
            return

        tiempo = self.ts.now()
        az, el, dist = self.control_antena.calcular_az_el(satelite, tiempo)

        if el < 0:
            texto = f"Satélite bajo el horizonte (El: {el:.1f}°). No se moverá la antena."
            self.root.after(0, lambda: lbl_estado.configure(text=texto))
            return

        texto = f"Az: {az:.1f}°  El: {el:.1f}°  Dist: {dist:.0f} km\nMoviendo motores..."
        self.root.after(0, lambda: lbl_estado.configure(text=texto))

        self.control_antena.apuntar_a(az, el)

        texto_final = f"Antena apuntando a Az: {az:.1f}°  El: {el:.1f}°"
        self.root.after(0, lambda: lbl_estado.configure(text=texto_final))


if __name__ == "__main__":
    root = tk.Tk()
    app = HMISimulator(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.control_antena.liberar(), root.destroy()))
    root.mainloop()

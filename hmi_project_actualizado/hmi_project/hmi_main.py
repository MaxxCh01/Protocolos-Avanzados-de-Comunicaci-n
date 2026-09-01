import threading
import tkinter as tk
from tkinter import font
from datetime import datetime

import numpy as np
from skyfield.api import load, wgs84
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import config
import spectro_sdr
from tle_manager import GestorTLE
from antenna_control import ControlAntena
from gpio_buttons import BotonesFisicos


class HMISimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("HMI - Proyecto METEOR-M UPIIZ-IPN (Datos Reales)")

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

        # Controla el loop de animación de la pantalla de trayectoria (para
        # poder detenerlo al salir de esa pantalla y no seguir dibujando
        # sobre widgets ya destruidos).
        self._animacion_trayectoria_activa = False

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

    def _config_satelite(self, etiqueta):
        """Devuelve la entrada de config.SATELITES que corresponde a la
        etiqueta mostrada en pantalla (p. ej. 'METEOR-M 2-3')."""
        for sat in config.SATELITES:
            if sat["etiqueta"] == etiqueta:
                return sat
        return None

    def _buscar_satelite(self, etiqueta):
        """Busca el objeto satélite (Skyfield/SGP4) en los TLE cargados,
        usando la 'clave' de config.SATELITES (el nombre tal como aparece
        en el archivo TLE de CelesTrak, p. ej. 'METEOR-M2 3')."""
        info = self._config_satelite(etiqueta)
        if not info:
            return None
        clave = info["clave"]
        for nombre_oficial, sat in self.por_nombre.items():
            if clave in nombre_oficial:
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
        for sat in config.SATELITES:
            etiqueta = sat["etiqueta"]
            btn = tk.Button(self.pantalla, text=etiqueta, font=self.font_normal, width=25, bg="#f0f0f0",
                            command=lambda s=etiqueta: self.mostrar_info_satelite(s))
            btn.pack(pady=6)
            botones.append(btn)

        botones.append(btn_regresar)
        self.registrar_menu(botones)

    def calcular_datos_satelite(self, etiqueta_satelite):
        """Altitud y velocidad geocéntricas (informativas) + datos estáticos de lanzamiento."""
        satelite = self._buscar_satelite(etiqueta_satelite)
        info = self._config_satelite(etiqueta_satelite) or {}

        if not satelite:
            print(f"Advertencia: No se encontró {etiqueta_satelite} en la base de datos TLE.")
            return "N/A", "N/A", info.get("lanzamiento", "Desconocido"), "N/A"

        tiempo_actual = self.ts.now()
        geocentrico = satelite.at(tiempo_actual)

        subpunto = wgs84.subpoint(geocentrico)
        altitud_km = subpunto.elevation.km

        vx, vy, vz = geocentrico.velocity.km_per_s
        velocidad_km_s = (vx**2 + vy**2 + vz**2) ** 0.5

        anio_lanzamiento = info.get("anio_lanzamiento", 0)
        anios_activo = (datetime.now().year - anio_lanzamiento) if anio_lanzamiento else 0

        return (f"{altitud_km:.2f} km", f"{velocidad_km_s:.2f} km/s",
                info.get("lanzamiento", "Desconocido"), str(anios_activo))

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
        self._animacion_trayectoria_activa = False  # por si venía una animación previa corriendo

        def _regresar():
            self._animacion_trayectoria_activa = False
            self.mostrar_info_satelite(self.satelite_actual)

        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                 command=_regresar)
        btn_regresar.place(relx=0.8, rely=0.05)

        tk.Label(self.pantalla, text=f"Trayectoria — {self.satelite_actual}",
                 bg="white", font=self.font_title).pack(pady=10)

        frame_graficas = tk.Frame(self.pantalla, bg="white")
        frame_graficas.pack(fill="both", expand=True, padx=20, pady=20)

        lbl_mapa = tk.Label(frame_graficas, text="Calculando órbita completa...",
                             bg="#f0f0f0", relief="sunken")
        lbl_mapa.pack(side="left", fill="both", expand=True, padx=5)

        lbl_polar = tk.Label(frame_graficas, text="Calculando pase orbital...",
                              bg="#f0f0f0", relief="sunken")
        lbl_polar.pack(side="right", fill="both", expand=True, padx=5)

        self.registrar_menu([btn_regresar])

        # El cálculo de la órbita completa, el pase (find_events) y las
        # gráficas pueden tardar; se hacen en un hilo aparte para no
        # congelar la interfaz.
        hilo = threading.Thread(
            target=self._trayectoria_worker, args=(frame_graficas, lbl_mapa, lbl_polar), daemon=True
        )
        hilo.start()

    def _trayectoria_worker(self, frame_graficas, lbl_mapa, lbl_polar):
        satelite = self._buscar_satelite(self.satelite_actual)
        if not satelite:
            texto = "No hay datos TLE de este satélite; no se puede calcular la trayectoria."
            self.root.after(0, lambda: (lbl_mapa.configure(text=texto), lbl_polar.configure(text="")))
            return

        tiempo = self.ts.now()
        pase = self.control_antena.calcular_pase(satelite, self.ts, tiempo)
        orbita_completa = self.control_antena.calcular_trayectoria_completa(satelite, self.ts, tiempo)

        self.root.after(0, self._dibujar_trayectoria, pase, orbita_completa, satelite, tiempo,
                         frame_graficas, lbl_mapa, lbl_polar)

    def _dibujar_trayectoria(self, pase, orbita_completa, satelite, tiempo, frame_graficas, lbl_mapa, lbl_polar):
        lbl_mapa.destroy()
        lbl_polar.destroy()

        # --- Mapa: órbita completa (traza en tierra de una vuelta entera) ---
        fig_mapa = Figure(figsize=(4, 4), dpi=100)
        ejes_mapa = fig_mapa.add_subplot(111)
        ejes_mapa.set_facecolor("#e8f0f8")
        ejes_mapa.plot(orbita_completa["longitudes"], orbita_completa["latitudes"],
                        color="#2ca02c", linewidth=1.3, alpha=0.7, label="Órbita completa")

        if pase is not None:
            # Resalta el tramo del pase visible (o próximo) sobre la órbita completa.
            ejes_mapa.plot(pase["longitudes"], pase["latitudes"], color="#ff7f0e",
                            linewidth=2.5, label="Pase sobre la antena")

        ejes_mapa.plot(config.LON_OBSERVADOR, config.LAT_OBSERVADOR, "^", color="red",
                        markersize=10, label="Antena")

        # Marcador animado del satélite (se actualiza en _animar_trayectoria)
        marcador_mapa, = ejes_mapa.plot([], [], "o", color="black", markersize=9,
                                         markerfacecolor="yellow", zorder=6, label=self.satelite_actual)

        ejes_mapa.set_xlim(-180, 180)
        ejes_mapa.set_ylim(-90, 90)
        ejes_mapa.set_xlabel("Longitud (°)", fontsize=8)
        ejes_mapa.set_ylabel("Latitud (°)", fontsize=8)
        ejes_mapa.set_title("Traza en tierra (órbita completa)", fontsize=10)
        ejes_mapa.grid(True, linestyle="--", alpha=0.5)
        ejes_mapa.legend(fontsize=6.5, loc="upper right")

        canvas_mapa = FigureCanvasTkAgg(fig_mapa, master=frame_graficas)
        canvas_mapa.draw()
        canvas_mapa.get_tk_widget().pack(side="left", fill="both", expand=True, padx=5)

        # --- Gráfica polar Azimut/Elevación (cenit al centro, horizonte al borde) ---
        fig_polar = Figure(figsize=(4, 4), dpi=100)
        ejes_polar = fig_polar.add_subplot(111, projection="polar")
        ejes_polar.set_theta_zero_location("N")
        ejes_polar.set_theta_direction(-1)
        ejes_polar.set_ylim(0, 90)
        ejes_polar.set_yticks([0, 30, 60, 90])
        ejes_polar.set_yticklabels(["90°", "60°", "30°", "0°"], fontsize=7)

        if pase is not None:
            azimuts_rad = np.radians(pase["azimuts"])
            radios = 90 - pase["elevaciones"]
            ejes_polar.plot(azimuts_rad, radios, color="#0055a4", linewidth=2, label="Pase")

        marcador_polar, = ejes_polar.plot([], [], "o", color="red", markersize=10,
                                           label="Posición actual", zorder=6)
        ejes_polar.legend(fontsize=6.5, loc="lower right")
        ejes_polar.set_title("Elevación / Azimut", fontsize=10)

        canvas_polar = FigureCanvasTkAgg(fig_polar, master=frame_graficas)
        canvas_polar.draw()
        canvas_polar.get_tk_widget().pack(side="right", fill="both", expand=True, padx=5)

        if pase is not None:
            estado = "en curso ahora mismo" if pase["en_curso"] else "próximo"
            texto_info = (
                f"Pase {estado}: AOS {pase['aos'].strftime('%H:%M:%S')} UTC  →  "
                f"LOS {pase['los'].strftime('%H:%M:%S')} UTC  "
                f"(elevación máxima {pase['elevacion_max']:.1f}°)"
            )
        else:
            texto_info = (f"{self.satelite_actual} no tiene ningún pase visible en las próximas 12 horas "
                          "desde esta ubicación (se muestra igual la órbita completa).")
        lbl_info = tk.Label(self.pantalla, text=texto_info, bg="white", font=self.font_normal)
        lbl_info.pack(pady=4)

        # --- Arranca la animación: el satélite se mueve en tiempo real ---
        self._animacion_trayectoria_activa = True
        self._animar_trayectoria(satelite, ejes_mapa, marcador_mapa, ejes_polar, marcador_polar,
                                  canvas_mapa, canvas_polar, lbl_info)

    def _animar_trayectoria(self, satelite, ejes_mapa, marcador_mapa, ejes_polar, marcador_polar,
                             canvas_mapa, canvas_polar, lbl_info):
        """Actualiza la posición del satélite sobre las gráficas cada 2
        segundos, usando SGP4 en tiempo real (no es una animación falsa:
        cada punto es una posición orbital calculada de verdad). Se detiene
        solo cuando el usuario sale de esta pantalla (btn_regresar pone
        self._animacion_trayectoria_activa = False)."""
        if not self._animacion_trayectoria_activa:
            return

        tiempo = self.ts.now()
        subpunto = wgs84.subpoint(satelite.at(tiempo))
        lat, lon = subpunto.latitude.degrees, subpunto.longitude.degrees
        az, el, dist = self.control_antena.calcular_az_el(satelite, tiempo)

        marcador_mapa.set_data([lon], [lat])

        if el > 0:
            marcador_polar.set_data([np.radians(az)], [90 - el])
        else:
            marcador_polar.set_data([], [])

        try:
            canvas_mapa.draw_idle()
            canvas_polar.draw_idle()
            visible = "SI, visible ahora" if el > 0 else "no, bajo el horizonte"
            lbl_info.configure(
                text=(f"Az: {az:6.1f}°   El: {el:6.1f}°   Dist: {dist:8.1f} km   "
                      f"Lat: {lat:6.2f}°   Lon: {lon:7.2f}°   Visible: {visible}")
            )
        except tk.TclError:
            # La pantalla ya no existe (el usuario navegó a otro lado); se detiene solo.
            self._animacion_trayectoria_activa = False
            return

        self.root.after(2000, self._animar_trayectoria, satelite, ejes_mapa, marcador_mapa,
                         ejes_polar, marcador_polar, canvas_mapa, canvas_polar, lbl_info)

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

        tk.Label(self.pantalla, text=f"Espectro SDR — {self.satelite_actual} ({tipo})",
                 bg="white", font=self.font_title).pack(pady=8)

        lbl_estado = tk.Label(self.pantalla, text="Capturando espectro...", bg="white", font=self.font_normal)
        lbl_estado.pack(pady=4)

        frame_grafica = tk.Frame(self.pantalla, bg="white")
        frame_grafica.pack(fill="both", expand=True, padx=20, pady=10)

        self.registrar_menu([btn_regresar])

        # La captura/FFT puede tardar (sobre todo con hardware real), así
        # que se hace en un hilo aparte para no congelar la interfaz.
        hilo = threading.Thread(
            target=self._espectro_worker, args=(tipo, lbl_estado, frame_grafica), daemon=True
        )
        hilo.start()

    def _espectro_worker(self, tipo, lbl_estado, frame_grafica):
        info = self._config_satelite(self.satelite_actual)
        satelite = self._buscar_satelite(self.satelite_actual)

        if not info or not satelite:
            texto = "No hay datos TLE de este satélite; no se puede calcular su frecuencia esperada."
            self.root.after(0, lambda: lbl_estado.configure(text=texto, fg="red"))
            return

        frecuencia_hz = info["frecuencia_lrpt_hz"]
        tiempo = self.ts.now()
        az, el, _dist = self.control_antena.calcular_az_el(satelite, tiempo)
        hay_pase = el > 0
        vel_radial = self.control_antena.calcular_velocidad_radial(satelite, tiempo) if hay_pase else 0.0

        resultado = spectro_sdr.analizar(
            frecuencia_central_hz=frecuencia_hz,
            frecuencia_esperada_hz=frecuencia_hz,
            hay_pase=hay_pase,
            velocidad_radial_km_s=vel_radial,
        )

        self.root.after(0, self._mostrar_resultado_espectro, tipo, resultado, az, el,
                         frecuencia_hz, vel_radial, lbl_estado, frame_grafica)

    def _mostrar_resultado_espectro(self, tipo, resultado, az, el, frecuencia_hz,
                                     vel_radial, lbl_estado, frame_grafica):
        c_km_s = spectro_sdr.VELOCIDAD_LUZ_KM_S
        corrimiento_doppler_hz = -vel_radial / c_km_s * frecuencia_hz

        frecuencias = resultado["frecuencias_hz"]
        if tipo == "sin efecto Doppler" and resultado["detectado"]:
            # Recentra el eje para mostrar la señal como se vería ya
            # compensado el corrimiento Doppler (lo que haría un receptor
            # con seguimiento de frecuencia activado).
            frecuencias = frecuencias + corrimiento_doppler_hz

        fig = Figure(figsize=(7, 3.2), dpi=100)
        ejes = fig.add_subplot(111)
        ejes.plot(frecuencias / 1000.0, resultado["potencia_db"], color="#00ff00", linewidth=1)
        ejes.axhline(resultado["piso_ruido_db"], color="#888888", linestyle="--", linewidth=0.8)
        ejes.set_facecolor("#001133")
        fig.patch.set_facecolor("#001133")
        ejes.tick_params(colors="white", labelsize=8)
        ejes.set_xlabel("Frecuencia relativa a 137.9 MHz (kHz)", color="white", fontsize=8)
        ejes.set_ylabel("Potencia (dB)", color="white", fontsize=8)
        for borde in ejes.spines.values():
            borde.set_color("white")

        canvas = FigureCanvasTkAgg(fig, master=frame_grafica)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        if el <= 0:
            lbl_estado.configure(
                text=(f"El satélite {self.satelite_actual} no está pasando en este momento "
                      f"(El: {el:.1f}°, bajo el horizonte). No se detecta ninguna señal."),
                fg="red")
            return

        if resultado["detectado"]:
            modo_txt = "RTL-SDR real" if resultado["modo"] == "hardware" else "modo simulación (sin RTL-SDR conectado)"
            lbl_estado.configure(
                text=(f"Señal detectada en {resultado['frecuencia_pico_hz']/1e6:.4f} MHz "
                      f"(SNR {resultado['snr_db']:.1f} dB, corrimiento Doppler "
                      f"{corrimiento_doppler_hz:+.0f} Hz — {modo_txt})."),
                fg="green")

            btn_trayectoria = tk.Button(self.pantalla, text="Ver trayectoria del pase",
                                         font=self.font_normal, bg="#f0f0f0",
                                         command=self.mostrar_trayectoria)
            btn_trayectoria.place(relx=0.32, rely=0.92)
            self.registrar_menu([btn_trayectoria] + self.widgets_menu)
        else:
            lbl_estado.configure(
                text=(f"El satélite está sobre el horizonte (Az: {az:.1f}°, El: {el:.1f}°) "
                      f"pero no se detecta su portadora en {frecuencia_hz/1e6:.4f} MHz."),
                fg="orange")

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

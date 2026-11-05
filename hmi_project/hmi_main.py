import threading
import os
import time
import tkinter as tk
from tkinter import font
from datetime import datetime

import numpy as np
from PIL import Image
from skyfield.api import load, wgs84
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import config
import spectro_sdr
import vista_3d
from tle_manager import GestorTLE
from antenna_control import ControlAntena
from gpio_buttons import BotonesFisicos


class HMISimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("HMI - Proyecto METEOR-M UPIIZ-IPN (Datos Reales)")

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

        self._animacion_trayectoria_activa = False
        self._animacion_espectro_activa = False
        self._vista3d = None

        self.widgets_menu = []
        self.indice_seleccion = 0

        print("Cargando datos astronómicos y TLE...")
        self.ts = load.timescale()
        self.gestor_tle = GestorTLE()
        self.por_nombre = {}
        self.origen_tle = None
        self.fecha_tle = None
        self._cargar_tle()

        # Posición inicial del observador (respaldo): config.py.
        # Se reemplaza por la del GPS del Pico cuando haya fix.
        self.lat_obs = config.LAT_OBSERVADOR
        self.lon_obs = config.LON_OBSERVADOR
        self.elev_obs = config.ELEV_OBSERVADOR_M
        self.fuente_pos = "config"
        self.observador = wgs84.latlon(self.lat_obs, self.lon_obs, self.elev_obs)
        self.control_antena = ControlAntena(self.observador)
        self.root.after(5000, self._actualizar_posicion_gps)

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
        for sat in config.SATELITES:
            if sat["etiqueta"] == etiqueta:
                return sat
        return None

    def _buscar_satelite(self, etiqueta):
        info = self._config_satelite(etiqueta)
        if not info:
            return None
        clave = info["clave"]
        for nombre_oficial, sat in self.por_nombre.items():
            if clave in nombre_oficial:
                return sat
        return None

    # ==========================================
    # POSICIÓN DEL OBSERVADOR (GPS del Pico)
    # ==========================================
    def _actualizar_posicion_gps(self):
        try:
            if self.control_antena.actualizar_desde_gps():
                obs = self.control_antena.observador
                self.observador = obs
                self.lat_obs = obs.latitude.degrees
                self.lon_obs = obs.longitude.degrees
                self.elev_obs = obs.elevation.m
                self.fuente_pos = "gps"
        except Exception as e:
            print(f"[GPS] No se pudo actualizar la posición: {e}")
        finally:
            # Siempre se reprograma, aunque haya fallado una lectura
            self.root.after(5000, self._actualizar_posicion_gps)

    # ==========================================
    # NAVEGACIÓN CON LOS 3 BOTONES FÍSICOS
    # ==========================================
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
        self.widgets_menu = widgets
        self.indice_seleccion = 0
        for w in widgets:
            w._bg_original = w.cget("bg")
        if widgets:
            self._resaltar(True)

    # ==========================================
    # PANELES FIJOS
    # ==========================================
    def limpiar_pantalla(self):
        if self._vista3d is not None:
            try:
                self._vista3d.cerrar()
            except Exception:
                pass
            self._vista3d = None
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

        btn_trayectoria_3d = tk.Button(frame_botones, text="Trayectoria 3D", font=self.font_normal, width=18,
                                        bg="#f0f0f0", command=self.abrir_trayectoria_3d)
        btn_trayectoria_3d.pack(pady=10)

        btn_espectro = tk.Button(frame_botones, text="Espectro SDR", font=self.font_normal, width=18,
                                  bg="#f0f0f0", command=self.mostrar_menu_espectro)
        btn_espectro.pack(pady=10)

        btn_apuntar = tk.Button(frame_botones, text="Apuntar antena", font=self.font_normal, width=18,
                                 bg="#f0f0f0", command=lambda: self.apuntar_antena(satelite))
        btn_apuntar.pack(pady=10)

        self.registrar_menu([btn_trayectoria, btn_trayectoria_3d, btn_espectro, btn_apuntar, btn_regresar])

    # ==========================================
    # TRAYECTORIA 3D — embebida en el HMI
    # ==========================================
    def abrir_trayectoria_3d(self):
        satelite = self._buscar_satelite(self.satelite_actual)
        if not satelite:
            self._error_trayectoria_3d("No hay datos TLE de este satélite.")
            return

        self.limpiar_pantalla()

        def _volver():
            self.mostrar_info_satelite(self.satelite_actual)

        self._vista3d = vista_3d.abrir_trayectoria_3d(
            self.pantalla,
            datos_provider=lambda: self._datos_orbita_para_3d(satelite),
            on_error=self._error_trayectoria_3d,
            on_back=_volver,
            embebido=True,
        )

    def _error_trayectoria_3d(self, mensaje):
        from tkinter import messagebox
        messagebox.showerror("Trayectoria 3D", mensaje)

    def _datos_orbita_para_3d(self, satelite):
        """Devuelve la órbita real (una vuelta, 240 puntos) y la posición
        ACTUAL como vectores ECEF en km, más los datos del observador."""
        ahora = self.ts.now()
        info = self._config_satelite(self.satelite_actual) or {}
        periodo_min = float(info.get("periodo_min", 101.3))

        color = info.get("color", "#00e5ff")
        if not (isinstance(color, str) and color.startswith("#") and len(color) == 7):
            color = "#00e5ff"

        minutos = np.linspace(0.0, periodo_min, 240)
        tiempos = self.ts.tt_jd(ahora.tt + minutos / (24.0 * 60.0))
        geo = satelite.at(tiempos)

        eci = np.asarray(geo.position.km, dtype=float)
        ecef = vista_3d.eci_a_ecef(eci, tiempos.ut1)

        orbita = [
            {"x": float(ecef[0][i]),
             "y": float(ecef[1][i]),
             "z": float(ecef[2][i])}
            for i in range(len(minutos))
        ]

        geo_ahora = satelite.at(ahora)
        ecef_ahora = vista_3d.eci_a_ecef(
            np.asarray(geo_ahora.position.km, dtype=float), ahora.ut1)
        sub_ahora = wgs84.subpoint(geo_ahora)

        return {
            "satelite": self.satelite_actual,
            "color": color,
            "observador": {
                "lat": float(self.lat_obs),
                "lon": float(self.lon_obs),
                "alt_km": self.elev_obs / 1000.0,
            },
            "orbita": orbita,
            "posicion_actual": {
                "x": float(ecef_ahora[0]),
                "y": float(ecef_ahora[1]),
                "z": float(ecef_ahora[2]),
                "lat": float(sub_ahora.latitude.degrees),
                "lon": float(sub_ahora.longitude.degrees),
                "alt_km": float(sub_ahora.elevation.km),
            },
        }

    # ==========================================
    # TRAYECTORIA 2D — mapa + polar (SGP4 real, matplotlib)
    # ==========================================
    def mostrar_trayectoria(self):
        self.limpiar_pantalla()
        self._animacion_trayectoria_activa = False

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

    @staticmethod
    def _graficar_traza(ejes, lons, lats, **kwargs):
        lons = np.asarray(lons)
        lats = np.asarray(lats)
        saltos = np.where(np.abs(np.diff(lons)) > 180)[0]
        segmentos = np.split(np.arange(len(lons)), saltos + 1)
        primero = True
        for seg in segmentos:
            if len(seg) < 2:
                continue
            kwargs_seg = dict(kwargs)
            if not primero:
                kwargs_seg.pop("label", None)
            ejes.plot(lons[seg], lats[seg], **kwargs_seg)
            primero = False

    _CACHE_IMAGEN_TIERRA = None

    def _imagen_tierra(self):
        if HMISimulator._CACHE_IMAGEN_TIERRA is None:
            ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "tierra.jpg")
            try:
                HMISimulator._CACHE_IMAGEN_TIERRA = np.asarray(Image.open(ruta))
            except Exception as e:
                print(f"[Trayectoria] No se pudo cargar assets/tierra.jpg como mapa de fondo: {e}")
                HMISimulator._CACHE_IMAGEN_TIERRA = False
        return HMISimulator._CACHE_IMAGEN_TIERRA if HMISimulator._CACHE_IMAGEN_TIERRA is not False else None

    def _dibujar_trayectoria(self, pase, orbita_completa, satelite, tiempo, frame_graficas, lbl_mapa, lbl_polar):
        lbl_mapa.destroy()
        lbl_polar.destroy()

        fig_mapa = Figure(figsize=(4, 4), dpi=100)
        ejes_mapa = fig_mapa.add_subplot(111)
        imagen_tierra = self._imagen_tierra()
        if imagen_tierra is not None:
            ejes_mapa.imshow(imagen_tierra, extent=[-180, 180, -90, 90], aspect="auto", zorder=0)
        else:
            ejes_mapa.set_facecolor("#e8f0f8")
        self._graficar_traza(ejes_mapa, orbita_completa["longitudes"], orbita_completa["latitudes"],
                              color="#2ca02c", linewidth=1.3, alpha=0.7, label="Órbita completa")

        if pase is not None:
            self._graficar_traza(ejes_mapa, pase["longitudes"], pase["latitudes"], color="#ff7f0e",
                                  linewidth=2.5, label="Pase sobre la antena")

        ejes_mapa.plot(self.lon_obs, self.lat_obs, "^", color="red",
                        markersize=10, label="Antena")

        marcador_mapa, = ejes_mapa.plot([], [], "o", color="black", markersize=9,
                                         markerfacecolor="yellow", zorder=6, label=self.satelite_actual)

        ejes_mapa.set_xlim(-180, 180)
        ejes_mapa.set_ylim(-90, 90)
        ejes_mapa.set_xlabel("Longitud (°)", fontsize=8)
        ejes_mapa.set_ylabel("Latitud (°)", fontsize=8)
        ejes_mapa.set_title("Traza en tierra (órbita completa)", fontsize=10)
        ejes_mapa.grid(True, linestyle="--", alpha=0.35, color="white" if imagen_tierra is not None else "black")
        ejes_mapa.legend(fontsize=6.5, loc="upper right", framealpha=0.85)

        canvas_mapa = FigureCanvasTkAgg(fig_mapa, master=frame_graficas)
        canvas_mapa.draw()
        canvas_mapa.get_tk_widget().pack(side="left", fill="both", expand=True, padx=5)

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

        self._animacion_trayectoria_activa = True
        self._animar_trayectoria(satelite, ejes_mapa, marcador_mapa, ejes_polar, marcador_polar,
                                  canvas_mapa, canvas_polar, lbl_info)

    def _animar_trayectoria(self, satelite, ejes_mapa, marcador_mapa, ejes_polar, marcador_polar,
                             canvas_mapa, canvas_polar, lbl_info):
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
            self._animacion_trayectoria_activa = False
            return

        self.root.after(1000, self._animar_trayectoria, satelite, ejes_mapa, marcador_mapa,
                         ejes_polar, marcador_polar, canvas_mapa, canvas_polar, lbl_info)

    # ==========================================
    # ESPECTRO SDR
    # ==========================================
    def mostrar_menu_espectro(self):
        self.limpiar_pantalla()
        self._animacion_espectro_activa = False

        info = self._config_satelite(self.satelite_actual)
        satelite = self._buscar_satelite(self.satelite_actual)
        if not info or not satelite:
            btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                      command=lambda: self.mostrar_info_satelite(self.satelite_actual))
            btn_regresar.place(relx=0.8, rely=0.05)
            tk.Label(self.pantalla, text="No hay datos TLE de este satélite; no se puede calcular su "
                                          "frecuencia esperada.", bg="white", font=self.font_normal, fg="red").pack(pady=40)
            self.registrar_menu([btn_regresar])
            return

        def _regresar():
            self._animacion_espectro_activa = False
            self.mostrar_info_satelite(self.satelite_actual)

        btn_regresar = tk.Button(self.pantalla, text="Regresar", font=self.font_normal, bg="#f0f0f0",
                                  command=_regresar)
        btn_regresar.place(relx=0.8, rely=0.05)

        self._doppler_compensado = tk.BooleanVar(value=False)
        btn_doppler = tk.Checkbutton(self.pantalla, text="Compensar corrimiento Doppler",
                                      variable=self._doppler_compensado, font=self.font_normal,
                                      bg="white")
        btn_doppler.place(relx=0.02, rely=0.05)

        tk.Label(self.pantalla, text=f"Espectro SDR — {self.satelite_actual} "
                                      f"({info['frecuencia_lrpt_hz']/1e6:.4f} MHz)",
                 bg="white", font=self.font_title).pack(pady=(45, 4))

        lbl_estado = tk.Label(self.pantalla, text="Iniciando captura...", bg="white", font=self.font_normal)
        lbl_estado.pack(pady=2)

        frame_grafica = tk.Frame(self.pantalla, bg="black")
        frame_grafica.pack(fill="both", expand=True, padx=15, pady=6)

        self.registrar_menu([btn_regresar, btn_doppler])

        fig = Figure(figsize=(9, 4), dpi=100)
        fig.patch.set_facecolor("black")
        ejes_linea = fig.add_subplot(1, 1, 1)
        fig.subplots_adjust(left=0.09, right=0.97, top=0.93, bottom=0.15)

        canvas = FigureCanvasTkAgg(fig, master=frame_grafica)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        self._animacion_espectro_activa = True
        self._animar_espectro(satelite, info, lbl_estado, fig, ejes_linea, canvas)

    def _animar_espectro(self, satelite, info, lbl_estado, fig, ejes_linea, canvas):
        if not self._animacion_espectro_activa:
            return

        frecuencia_hz = info["frecuencia_lrpt_hz"]
        tiempo = self.ts.now()
        az, el, _dist = self.control_antena.calcular_az_el(satelite, tiempo)
        hay_pase = el > 0
        vel_radial = self.control_antena.calcular_velocidad_radial(satelite, tiempo) if hay_pase else 0.0

        def _worker():
            resultado = spectro_sdr.analizar(
                frecuencia_central_hz=frecuencia_hz,
                frecuencia_esperada_hz=frecuencia_hz,
                hay_pase=hay_pase,
                velocidad_radial_km_s=vel_radial,
            )
            if self._animacion_espectro_activa:
                self.root.after(0, self._dibujar_espectro, resultado, az, el, hay_pase, vel_radial,
                                 frecuencia_hz, satelite, info, lbl_estado, fig, ejes_linea, canvas)

        threading.Thread(target=_worker, daemon=True).start()

    def _dibujar_espectro(self, resultado, az, el, hay_pase, vel_radial, frecuencia_hz, satelite, info,
                           lbl_estado, fig, ejes_linea, canvas):
        if not self._animacion_espectro_activa:
            return

        c_km_s = spectro_sdr.VELOCIDAD_LUZ_KM_S
        corrimiento_doppler_hz = -vel_radial / c_km_s * frecuencia_hz if hay_pase else 0.0
        compensar = self._doppler_compensado.get()

        frecuencias = resultado["frecuencias_hz"].copy()
        frecuencia_marca_hz = 0.0
        if compensar and hay_pase:
            frecuencias = frecuencias + corrimiento_doppler_hz
            frecuencia_marca_hz = 0.0
        elif hay_pase:
            frecuencia_marca_hz = corrimiento_doppler_hz

        ejes_linea.clear()
        ejes_linea.set_facecolor("#00081a")
        ejes_x_khz = frecuencias / 1000.0
        ejes_linea.fill_between(ejes_x_khz, resultado["potencia_db"], resultado["piso_ruido_db"] - 8,
                                 color="#3399ff", alpha=0.35)
        ejes_linea.plot(ejes_x_khz, resultado["potencia_db"], color="#cfeeff", linewidth=1)
        ejes_linea.axhline(resultado["piso_ruido_db"], color="#888888", linestyle="--", linewidth=0.7)

        tolerancia_khz = config.SDR_TOLERANCIA_DOPPLER_HZ / 1000.0
        marca_khz = frecuencia_marca_hz / 1000.0
        ejes_linea.axvspan(marca_khz - tolerancia_khz, marca_khz + tolerancia_khz,
                            color="white", alpha=0.10)
        ejes_linea.axvline(marca_khz, color="#ff3333", linewidth=1)

        piso = resultado["piso_ruido_db"]
        ejes_linea.set_ylim(piso - 5, piso + 40)
        ejes_linea.set_xlim(ejes_x_khz.min(), ejes_x_khz.max())
        ejes_linea.tick_params(colors="white", labelsize=8)
        ejes_linea.set_ylabel("Potencia relativa (dB)", color="white", fontsize=8)
        ejes_linea.set_xlabel(f"Frecuencia relativa a {frecuencia_hz/1e6:.4f} MHz (kHz)",
                               color="white", fontsize=8)
        for borde in ejes_linea.spines.values():
            borde.set_color("#334455")
        ejes_linea.grid(color="#223344", linestyle="-", linewidth=0.5, alpha=0.6)

        try:
            canvas.draw_idle()
        except tk.TclError:
            self._animacion_espectro_activa = False
            return

        if resultado["modo"] == "sin_hardware":
            lbl_estado.configure(
                text=("SDR no conectado — mostrando solo ruido de referencia "
                      "(conecta un RTL-SDR para detección real)."),
                fg="#888888")
        elif not hay_pase:
            lbl_estado.configure(
                text=(f"{self.satelite_actual} no está pasando ahora (El: {el:.1f}°, bajo el horizonte). "
                      "SDR conectado, sin señal esperada."),
                fg="#888888")
        elif resultado["detectado"]:
            lbl_estado.configure(
                text=(f"Señal detectada en {resultado['frecuencia_pico_hz']/1e6:.4f} MHz "
                      f"(SNR {resultado['snr_db']:.1f} dB). Corrimiento Doppler estimado: "
                      f"{corrimiento_doppler_hz:+.0f} Hz."),
                fg="#33cc55")
        else:
            lbl_estado.configure(
                text=(f"SDR conectado. Satélite sobre el horizonte (Az {az:.1f}°, El {el:.1f}°) "
                      f"pero no se detecta portadora en {frecuencia_hz/1e6:.4f} MHz."),
                fg="#ff9900")

        self.root.after(120, self._animar_espectro, satelite, info, lbl_estado, fig, ejes_linea, canvas)

    # ==========================================
    # APUNTADO DE ANTENA
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

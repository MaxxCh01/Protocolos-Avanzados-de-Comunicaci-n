# =====================================================================
#  vista_3d.py — Trayectoria 3D embebida (Tkinter Canvas puro, sin turtle)
#  - Esfera terrestre con textura real, con fallbacks robustos
#  - Órbita y satélite en ECEF (mismo marco -> geometría correcta)
#  - Estación terrena siempre visible (resaltada u oculta)
#  - Botón "Regresar" propio, con callback on_back
# =====================================================================
from __future__ import annotations

import math
import os
import ssl
import tkinter as tk
from urllib.request import urlopen, Request

import numpy as np

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


R_TIERRA_KM = 6371.0
_RADIO_OBJETIVO_FRAC = 0.40
_LUZ = (1.0, 0.35, 0.4)

# Varias fuentes posibles para la textura (equirectangular, lon 0 al centro)
_URLS_TEX = (
    # Wikimedia (NASA Blue Marble, 1024x512)
    "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/"
    "Land_ocean_ice_2048.jpg/1024px-Land_ocean_ice_2048.jpg",
    # Wikimedia (Blue Marble, 2048x1024, por si la anterior cambia)
    "https://upload.wikimedia.org/wikipedia/commons/c/cd/Land_ocean_ice_2048.jpg",
    # Solar System Scope (2k daymap)
    "https://www.solarsystemscope.com/textures/download/2k_earth_daymap.jpg",
    # GitHub espejo (webgl-earth)
    "https://raw.githubusercontent.com/turban/webgl-earth/master/"
    "images/2_no_clouds_4k.jpg",
)

_NOMBRES_TEX_LOCAL = (
    "earth.jpg", "earth.png", "tierra.jpg", "tierra.png",
    "earth_texture.jpg", "earth_texture.png",
    "land_ocean_ice_2048.jpg",
    "assets/tierra.jpg", "assets/earth.jpg",
    "assets/tierra.png", "assets/earth.png",
)


# ---------------------------------------------------------------------
#  Utilidades astronómicas
# ---------------------------------------------------------------------
def gmst_rad(jd_ut1):
    jd_ut1 = np.asarray(jd_ut1, dtype=float)
    d = jd_ut1 - 2451545.0
    T = d / 36525.0
    g = (280.46061837 + 360.98564736629 * d
         + 0.000387933 * T * T - (T ** 3) / 38710000.0)
    return np.radians(np.mod(g, 360.0))


def eci_a_ecef(xyz_km, jd_ut1):
    xyz = np.asarray(xyz_km, dtype=float)
    g = gmst_rad(jd_ut1)
    c, s = np.cos(g), np.sin(g)
    x, y, z = xyz[0], xyz[1], xyz[2]
    return np.array([c * x + s * y,
                     -s * x + c * y,
                     z])


def geodetico_a_ecef(lat_deg, lon_deg, alt_km=0.0, r_tierra=R_TIERRA_KM):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    r = r_tierra + alt_km
    return (r * math.cos(lat) * math.cos(lon),
            r * math.cos(lat) * math.sin(lon),
            r * math.sin(lat))


def _mezclar(hex_color, factor):
    try:
        c = hex_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        f = lambda v: max(0, min(255, int(v * factor)))
        return "#{:02x}{:02x}{:02x}".format(f(r), f(g), f(b))
    except Exception:
        return hex_color


# ---------------------------------------------------------------------
#  Carga de textura (local -> descarga -> procedural)
# ---------------------------------------------------------------------
def _textura_procedural(ancho=1024, alto=512):
    """Genera una textura equirectangular aproximada de la Tierra.

    No es perfecta pero permite ver 'continentes' verde-marrón sobre
    océanos azules. Se usa solo cuando fallan los archivos locales y la
    descarga.
    """
    W, H = ancho, alto
    img = np.zeros((H, W, 3), dtype=np.float32)

    # Océano base con gradiente (más oscuro en los polos)
    lat = np.linspace(90.0, -90.0, H)[:, None]
    lon = np.linspace(-180.0, 180.0, W)[None, :]
    oc = np.zeros((H, W, 3), dtype=np.float32)
    oc[..., 2] = 110 + 40 * np.cos(np.radians(lat))     # azul
    oc[..., 1] = 55 + 25 * np.cos(np.radians(lat))
    oc[..., 0] = 15
    img[:] = oc

    # "Continentes" definidos a mano en (lat, lon, radio_lat, radio_lon)
    continentes = [
        (55, -100, 22, 40),   # Norteamérica
        (10, -75, 12, 18),    # Centroamérica / Caribe
        (-15, -60, 25, 22),   # Sudamérica
        (10, 20, 30, 40),     # África norte
        (-15, 25, 28, 25),    # África sur
        (50, 15, 20, 30),     # Europa
        (45, 90, 30, 55),     # Asia central
        (25, 110, 20, 30),    # Asia oriental
        (-25, 135, 15, 22),   # Australia
        (75, -40, 12, 25),    # Groenlandia
        (-80, 0, 10, 360),    # Antártida (banda)
    ]
    tierra_rgb = (85, 120, 55)   # verde-marrón
    for clat, clon, rlat, rlon in continentes:
        dlat = lat - clat
        dlon = lon - clon
        # Ajuste por longitud (más fino cerca de polos)
        dlon_corr = dlon * np.cos(np.radians(np.clip(lat, -80, 80)))
        dist = (dlat / rlat) ** 2 + (dlon_corr / (rlon * 0.55)) ** 2
        mask = dist <= 1.0
        factor = np.where(mask, 1.0 - 0.35 * dist, 0.0)
        for k in range(3):
            img[..., k] = img[..., k] * (1 - factor) + tierra_rgb[k] * factor

    # Casquetes polares blancos
    lat_arr = np.linspace(90.0, -90.0, H)[:, None] * np.ones((1, W))
    polar_n = np.clip((lat_arr - 65.0) / 25.0, 0.0, 1.0)
    polar_s = np.clip((-lat_arr - 65.0) / 25.0, 0.0, 1.0)
    polar = np.maximum(polar_n, polar_s)
    for k in range(3):
        img[..., k] = img[..., k] * (1 - polar) + 235.0 * polar

    return np.clip(img, 0, 255).astype(np.uint8)


def _descargar_textura(destino):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for url in _URLS_TEX:
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=20, context=ctx) as r:
                data = r.read()
            if len(data) < 20000:      # demasiado pequeño, seguro es HTML
                continue
            with open(destino, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"[vista_3d] Fallo descarga {url}: {e}")
            continue
    return False


def _cargar_textura():
    """Devuelve (ndarray HxWx3, es_real:bool)."""
    if not _PIL_OK:
        return None, False

    base = os.path.dirname(os.path.abspath(__file__))

    # 1) archivos locales
    for nombre in _NOMBRES_TEX_LOCAL:
        ruta = os.path.join(base, nombre)
        if os.path.isfile(ruta):
            try:
                arr = np.asarray(Image.open(ruta).convert("RGB"))
                print(f"[vista_3d] Textura cargada desde {ruta}")
                return arr, True
            except Exception:
                continue

    # 2) descargar y cachear
    cache = os.path.join(base, "earth_texture.jpg")
    if os.path.isfile(cache):
        try:
            arr = np.asarray(Image.open(cache).convert("RGB"))
            print(f"[vista_3d] Textura cargada desde caché {cache}")
            return arr, True
        except Exception:
            pass
    else:
        if _descargar_textura(cache):
            try:
                arr = np.asarray(Image.open(cache).convert("RGB"))
                print(f"[vista_3d] Textura descargada -> {cache}")
                return arr, True
            except Exception:
                pass

    # 3) procedural
    print("[vista_3d] Usando textura procedural (sin archivo ni internet).")
    return _textura_procedural(), False


# ---------------------------------------------------------------------
#  Vista 3D
# ---------------------------------------------------------------------
class VistaTrayectoria3D:
    _vivas = []

    def __init__(self, parent, datos_provider, on_error=None,
                 on_back=None, intervalo_ms=1000, embebido=True):
        self.parent = parent
        self.datos_provider = datos_provider
        self.on_error = on_error
        self.on_back = on_back
        self.intervalo_ms = intervalo_ms

        # cámara
        self.ang_x = 22.0
        self.ang_y = -35.0
        self.zoom = 1.0

        # tamaño (se actualiza por <Configure>)
        self.ancho = 800
        self.alto = 600

        # estado
        self._arrastrando = False
        self._ux = self._uy = 0.0
        self._after = None
        self._viva = True
        self._error_mostrado = False
        self._datos = None
        self._escala = 1.0
        self._earth_photo = None

        self._textura, self._textura_real = _cargar_textura()

        # ---- contenedor ----
        if embebido:
            self.win = None
            self.frame = tk.Frame(parent, bg="black")
            self.frame.pack(fill="both", expand=True)
        else:
            self.win = tk.Toplevel(parent)
            self.win.title("Trayectoria 3D — SGP4 (ECEF)")
            self.win.configure(bg="black")
            self.win.geometry("880x720")
            self.win.protocol("WM_DELETE_WINDOW", self.cerrar)
            self.frame = self.win

        # ---- canvas ----
        self.canvas = tk.Canvas(self.frame, bg="black",
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # ---- botón Regresar (encima del canvas) ----
        self.btn_back = tk.Button(
            self.frame, text="‹ Regresar",
            font=("Segoe UI", 10, "bold"),
            bg="#2a2a2a", fg="white",
            activebackground="#3a3a3a", activeforeground="white",
            bd=0, padx=10, pady=4, relief="flat",
            highlightthickness=0,
            command=self._al_pulsar_back,
        )
        self.btn_back.place(relx=1.0, x=-10, y=10, anchor="ne")
        try:
            self.btn_back.lift()
        except Exception:
            pass

        self._bind_eventos()
        VistaTrayectoria3D._vivas.append(self)

        self.frame.after(80, self._iniciar)

    # -----------------------------------------------------------------
    def _al_pulsar_back(self):
        if self.on_back is not None:
            try:
                self.on_back()
                return
            except Exception:
                pass
        self.cerrar()

    def _iniciar(self):
        self._actualizar_tamano()
        self._loop()

    def _actualizar_tamano(self):
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
        except tk.TclError:
            return
        if w >= 50 and h >= 50:
            self.ancho, self.alto = w, h

    def _bind_eventos(self):
        c = self.canvas
        c.bind("<ButtonPress-1>",   self._on_press)
        c.bind("<B1-Motion>",       self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<MouseWheel>",      self._on_wheel)
        c.bind("<Button-4>", lambda e: self._zoom(1.12))
        c.bind("<Button-5>", lambda e: self._zoom(1 / 1.12))
        c.bind("<Configure>",       self._on_configure)
        target = self.win if self.win else self.canvas
        target.bind("<Escape>", lambda e: self._al_pulsar_back())
        target.bind("<r>",      lambda e: self._reset_camara())
        target.bind("<R>",      lambda e: self._reset_camara())
        target.bind("<BackSpace>", lambda e: self._al_pulsar_back())
        try:
            target.focus_set()
        except Exception:
            pass

    def _on_configure(self, ev):
        if ev.width >= 50 and ev.height >= 50:
            if ev.width != self.ancho or ev.height != self.alto:
                self.ancho, self.alto = ev.width, ev.height
                self._render()

    # ---------------- eventos ratón -----------------
    def _on_press(self, ev):
        self._arrastrando = True
        self._ux, self._uy = ev.x, ev.y

    def _on_release(self, _ev):
        self._arrastrando = False

    def _on_drag(self, ev):
        if not self._arrastrando:
            return
        dx = ev.x - self._ux
        dy = ev.y - self._uy
        self._ux, self._uy = ev.x, ev.y
        self.ang_y += dx * 0.45
        self.ang_x += dy * 0.45
        self.ang_x = max(-89.0, min(89.0, self.ang_x))
        self._render()

    def _on_wheel(self, ev):
        self._zoom(1.12 if ev.delta > 0 else 1 / 1.12)

    def _zoom(self, f):
        self.zoom = max(0.5, min(3.0, self.zoom * f))
        self._render()

    def _reset_camara(self):
        self.ang_x, self.ang_y, self.zoom = 22.0, -35.0, 1.0
        self._render()

    # -----------------------------------------------------------------
    #  Proyección ortográfica -> coords de canvas
    # -----------------------------------------------------------------
    def _proyectar(self, x_km, y_km, z_km):
        e = self._escala
        X = x_km * e
        Y = z_km * e
        Z = y_km * e

        ry = math.radians(self.ang_y)
        cy, sy = math.cos(ry), math.sin(ry)
        x1 = X * cy + Z * sy
        z1 = -X * sy + Z * cy

        rx = math.radians(self.ang_x)
        cx, sx = math.cos(rx), math.sin(rx)
        y2 = Y * cx - z1 * sx
        z2 = Y * sx + z1 * cx

        return x1 + self.ancho / 2.0, self.alto / 2.0 - y2, z2

    def _proyectar_ecef(self, v):
        return self._proyectar(v[0], v[1], v[2])

    # -----------------------------------------------------------------
    def _trazo(self, pts, color, rpx, ancho=2):
        r2 = rpx * rpx
        cx0 = self.ancho / 2.0
        cy0 = self.alto / 2.0
        for i in range(len(pts) - 1):
            x0, y0, z0 = pts[i]
            x1, y1, z1 = pts[i + 1]
            v0 = (z0 >= 0.0) or ((x0 - cx0) ** 2 + (y0 - cy0) ** 2 >= r2)
            v1 = (z1 >= 0.0) or ((x1 - cx0) ** 2 + (y1 - cy0) ** 2 >= r2)
            if v0 and v1:
                self.canvas.create_line(x0, y0, x1, y1,
                                        fill=color, width=ancho,
                                        capstyle="round")

    # -----------------------------------------------------------------
    #  Esfera con textura
    # -----------------------------------------------------------------
    def _renderizar_tierra(self):
        if not _PIL_OK:
            return
        rpx = R_TIERRA_KM * self._escala
        if rpx < 4:
            return

        r_int = int(math.ceil(rpx)) + 1
        side = 2 * r_int + 1

        I, J = np.indices((side, side))
        X = (J - r_int).astype(np.float32)
        Y = (r_int - I).astype(np.float32)
        D2 = X * X + Y * Y
        mask = D2 <= rpx * rpx
        Z = np.sqrt(np.maximum(rpx * rpx - D2, 0.0)).astype(np.float32)

        rx = math.radians(self.ang_x)
        ry = math.radians(self.ang_y)
        cxs, sxs = math.cos(rx), math.sin(rx)
        cys, sys_ = math.cos(ry), math.sin(ry)

        Ye = cxs * Y + sxs * Z
        z1 = -sxs * Y + cxs * Z
        Xe = cys * X - sys_ * z1
        Ze = sys_ * X + cys * z1

        e = self._escala
        x_ecef = Xe / e
        y_ecef = Ze / e
        z_ecef = Ye / e

        R = np.sqrt(x_ecef ** 2 + y_ecef ** 2 + z_ecef ** 2) + 1e-9
        lat = np.arcsin(np.clip(z_ecef / R, -1.0, 1.0))
        lon = np.arctan2(y_ecef, x_ecef)

        if self._textura is not None:
            th, tw = self._textura.shape[:2]
            u = ((lon / (2.0 * math.pi)) + 0.5) * (tw - 1)
            v = (0.5 - lat / math.pi) * (th - 1)
            ui = np.clip(u.astype(np.int32), 0, tw - 1)
            vi = np.clip(v.astype(np.int32), 0, th - 1)
            rgb = self._textura[vi, ui].astype(np.float32)
        else:
            rgb = np.zeros((side, side, 3), dtype=np.float32)
            rgb[..., 0] = 20
            rgb[..., 1] = 55
            rgb[..., 2] = 100

        # ----- Iluminación suave: TODO el planeta visible -----
        nx = x_ecef / R
        ny = y_ecef / R
        nz = z_ecef / R
        lx, ly, lz = _LUZ
        ln = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / ln, ly / ln, lz / ln
        dot = nx * lx + ny * ly + nz * lz          # [-1, 1]

        # Mapeo: [-1, 1] -> [0.72, 1.08]. El "lado oscuro" sigue visible,
        # el lado iluminado se ve brillante. Nunca cae por debajo de 0.72.
        lum = 0.72 + 0.36 * (0.5 + 0.5 * dot)

        # Un pelín de "fresnel" en los bordes para dar volumen sin oscurecer
        d = np.sqrt(D2)
        rim = np.clip((rpx - d) / 3.0, 0.0, 1.0)
        lum += (1.0 - rim) * 0.15                  # aclara el borde
        lum = np.clip(lum, 0.0, 1.20)
        rgb *= lum[..., None]

        # Aplicar rim también en alpha para bordes suaves (evita dientes)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        alpha = np.where(mask, 255, 0).astype(np.uint8)
        alpha = (alpha.astype(np.float32) * rim).astype(np.uint8)
        arr = np.dstack([rgb, alpha])

        self._earth_photo = ImageTk.PhotoImage(Image.fromarray(arr, "RGBA"))
        self.canvas.create_image(self.ancho / 2.0, self.alto / 2.0,
                                 anchor="center",
                                 image=self._earth_photo,
                                 tags="tierra")
        self.canvas.tag_lower("tierra")

    # -----------------------------------------------------------------
    def _loop(self):
        if not self._viva:
            return
        try:
            self._datos = self.datos_provider()
        except Exception as exc:
            if self.on_error and not self._error_mostrado:
                self._error_mostrado = True
                self.on_error(f"No se pudo calcular la órbita: {exc}")
            self.cerrar()
            return
        try:
            self._render()
        except Exception:
            import traceback
            traceback.print_exc()
        self._after = self.frame.after(self.intervalo_ms, self._loop)

    # -----------------------------------------------------------------
    def _render(self):
        d = self._datos
        if not d:
            return
        c = self.canvas
        c.delete("all")
        self._earth_photo = None

        orb = d.get("orbita") or []
        color = d.get("color", "#00e5ff")

        r_max = R_TIERRA_KM
        for p in orb:
            r = math.sqrt(p["x"] ** 2 + p["y"] ** 2 + p["z"] ** 2)
            if r > r_max:
                r_max = r

        radio_objetivo_px = min(self.ancho, self.alto) * _RADIO_OBJETIVO_FRAC
        self._escala = (radio_objetivo_px / r_max) * self.zoom
        rpx = R_TIERRA_KM * self._escala

        # 1) Esfera
        self._renderizar_tierra()

        # 2) Huella terrestre
        if orb:
            pts_huella = []
            for p in orb:
                r = math.sqrt(p["x"] ** 2 + p["y"] ** 2 + p["z"] ** 2)
                if r <= 0:
                    continue
                k = R_TIERRA_KM / r
                pts_huella.append(self._proyectar(p["x"] * k, p["y"] * k, p["z"] * k))
            self._trazo(pts_huella, _mezclar(color, 0.55), rpx, ancho=2)

        # 3) Órbita
        if len(orb) > 1:
            pts = [self._proyectar(p["x"], p["y"], p["z"]) for p in orb]
            self._trazo(pts, color, rpx, ancho=2)

        # 4) Observador (SIEMPRE se dibuja; resaltado u oculto)
        obs = d.get("observador")
        if obs:
            v = geodetico_a_ecef(obs["lat"], obs["lon"], obs.get("alt_km", 0.0))
            px, py, pz = self._proyectar_ecef(v)
            visible = pz >= 0
            # Pequeña línea vertical en el punto para que se vea sobre el mar
            self._dibujar_estacion(px, py, visible)

        # 5) Satélite
        pa = d.get("posicion_actual")
        if pa:
            px, py, pz = self._proyectar(pa["x"], pa["y"], pa["z"])
            cx0 = self.ancho / 2.0
            cy0 = self.alto / 2.0
            visible = (pz >= 0.0) or ((px - cx0) ** 2 + (py - cy0) ** 2 >= rpx * rpx)
            if visible:
                c.create_line(cx0, cy0, px, py,
                              fill=_mezclar(color, 0.45), width=1)

                r = math.sqrt(pa["x"] ** 2 + pa["y"] ** 2 + pa["z"] ** 2)
                if r > 0:
                    k = R_TIERRA_KM / r
                    sx, sy, sz = self._proyectar(pa["x"] * k, pa["y"] * k, pa["z"] * k)
                    if sz >= 0:
                        c.create_oval(sx - 3, sy - 3, sx + 3, sy + 3,
                                      fill="#ffd400", outline="")

                c.create_oval(px - 6, py - 6, px + 6, py + 6,
                              fill=color, outline="")
                c.create_oval(px - 2.5, py - 2.5, px + 2.5, py + 2.5,
                              fill="white", outline="")
                c.create_text(px + 13, py + 12,
                              text=d.get("satelite", "satélite"),
                              fill="white", anchor="w",
                              font=("Segoe UI", 9, "bold"))

        # 6) HUD
        self._dibujar_hud(d)

        # Re-alzar el botón Regresar por si el canvas lo tapó
        try:
            self.btn_back.lift()
        except Exception:
            pass

    # -----------------------------------------------------------------
    def _dibujar_estacion(self, px, py, visible):
        c = self.canvas
        if visible:
            fill = "#ff2222"
            outline = "#ffffff"
            label_col = "#ffdddd"
        else:
            fill = "#553333"
            outline = "#aa7777"
            label_col = "#886666"

        # Marcador tipo "pin" (rombo) para distinguirlo del satélite
        s = 6
        c.create_polygon(px, py - s,
                         px + s, py,
                         px, py + s,
                         px - s, py,
                         fill=fill, outline=outline, width=1)
        # Cruz
        c.create_line(px - s - 3, py, px + s + 3, py, fill=outline)
        c.create_line(px, py - s - 3, px, py + s + 3, fill=outline)

        texto = "Estación" if visible else "Estación (oculta)"
        c.create_text(px + 12, py - 12, text=texto,
                      fill=label_col, anchor="w",
                      font=("Segoe UI", 8, "bold"))

    # -----------------------------------------------------------------
    def _dibujar_hud(self, d):
        c = self.canvas
        x0 = 14
        y0 = 14

        c.create_text(x0, y0,
                      text=f"{d.get('satelite','')}   ·   SGP4 / TLE real   ·   marco ECEF",
                      fill="#9fe8ff", anchor="nw",
                      font=("Segoe UI", 11, "bold"))

        pa = d.get("posicion_actual") or {}
        if pa:
            c.create_text(x0, y0 + 20,
                          text=(f"Lat {pa.get('lat',0):+.3f}°   "
                                f"Lon {pa.get('lon',0):+.3f}°   "
                                f"Alt {pa.get('alt_km',0):.1f} km"),
                          fill="#c9d6e2", anchor="nw",
                          font=("Segoe UI", 9))

        c.create_text(x0, self.alto - 14,
                      text="[arrastrar] rotar   ·   [rueda] zoom   ·   [R] reset",
                      fill="#6c8090", anchor="sw",
                      font=("Segoe UI", 8))

        if not _PIL_OK:
            c.create_text(x0, self.alto - 30,
                          text="Instala Pillow para ver la Tierra con textura:  pip install pillow",
                          fill="#ff7a7a", anchor="sw",
                          font=("Segoe UI", 8))
        elif not self._textura_real:
            c.create_text(x0, self.alto - 30,
                          text=("Textura procedural (no se encontró earth_texture.jpg "
                                "ni se pudo descargar; colócala junto a vista_3d.py)"),
                          fill="#ffcc66", anchor="sw",
                          font=("Segoe UI", 8))

    # -----------------------------------------------------------------
    def cerrar(self):
        if not self._viva:
            return
        self._viva = False
        if self._after is not None:
            try:
                self.frame.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        try:
            if self in VistaTrayectoria3D._vivas:
                VistaTrayectoria3D._vivas.remove(self)
        except Exception:
            pass
        try:
            if self.win is not None:
                self.win.destroy()
            else:
                self.frame.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------
#  API compatible con el HMI
# ---------------------------------------------------------------------
def abrir_trayectoria_3d(parent, datos_provider, on_error=None,
                          on_back=None, embebido=True):
    return VistaTrayectoria3D(parent, datos_provider, on_error,
                              on_back=on_back, embebido=embebido)

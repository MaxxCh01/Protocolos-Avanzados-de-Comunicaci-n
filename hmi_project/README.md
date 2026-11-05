# HMI METEOR-M para Raspberry Pi 4B

Proyecto listo para correr directamente en el Raspberry Pi: HMI en pantalla
completa, navegación con 3 botones físicos, descarga de TLE con respaldo
offline en caché, cálculo orbital con SGP4 (vía Skyfield), detección real
de señal LRPT vía RTL-SDR con trayectoria del pase, y movimiento de un
motor de pasos (azimut) + servo (elevación) para apuntar la antena.

Monitorea los satélites meteorológicos rusos **METEOR-M 2-3** y
**METEOR-M 2-4**, que transmiten LRPT en 137.900 MHz (con 137.100 MHz como
frecuencia de respaldo).

## 1. Estructura del proyecto

```
hmi_project/
├── hmi_main.py          # Programa principal (ejecutar este)
├── config.py             # Pines GPIO, ubicación de la antena, satélites, URL de TLE
├── tle_manager.py         # Descarga TLE / respaldo en caché local
├── antenna_control.py     # Cálculo de az/el, velocidad radial, pase completo + motor/servo
├── spectro_sdr.py         # Captura/análisis de espectro (RTL-SDR real o simulación)
├── gpio_buttons.py        # Lectura de los 3 botones físicos
├── requirements.txt
└── hmi-autostart.desktop  # Arranque automático
```

## 2. Instalación en el Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip python3-tk python3-rpi.gpio python3-pil.imagetk

# Copia la carpeta hmi_project a tu carpeta personal (usa tu propio usuario,
# no necesariamente "pi" — por ejemplo /home/maxchqto/hmi_project)
cd ~/hmi_project
pip3 install -r requirements.txt --break-system-packages
```

`python3-pil.imagetk` es necesario para que matplotlib pueda dibujar
dentro de las ventanas de Tkinter (espectro y trayectoria); en Debian/
Raspberry Pi OS este submódulo de Pillow viene separado del paquete base.

La ruta donde se guarda la caché de TLE (`RUTA_CACHE_TLE` en `config.py`)
se calcula automáticamente a partir de `$HOME`, así que funciona sin
importar el nombre de tu usuario.

Antes de correrlo, edita `config.py`:
- `LAT_OBSERVADOR`, `LON_OBSERVADOR`, `ELEV_OBSERVADOR_M`: coordenadas reales de tu antena.
- Pines GPIO si tu cableado es distinto al sugerido.

Prueba manual:
```bash
python3 hmi_main.py
```
(Presiona `Esc` para salir de pantalla completa mientras pruebas.)

## 3. Conexiones de hardware

### Botones físicos (con pull-up interno, no necesitan resistencias)
| Botón   | GPIO (BCM) | Otro extremo |
|---------|-----------|--------------|
| ARRIBA  | GPIO 5    | GND          |
| ENTER   | GPIO 6    | GND          |
| ABAJO   | GPIO 13   | GND          |

### Motor de pasos 28BYJ-48 + driver ULN2003 (AZIMUT)
| Driver ULN2003 | GPIO Raspberry (BCM) |
|----------------|----------------------|
| IN1            | GPIO 17              |
| IN2            | GPIO 27              |
| IN3            | GPIO 22              |
| IN4            | GPIO 23              |
| VCC del driver | **Fuente externa de 5V**, no el pin 5V del Pi |
| GND            | GND común con el Raspberry |

### Servomotor (ELEVACIÓN)
| Servo   | Conexión |
|---------|----------|
| Señal   | GPIO 18 (PWM por hardware) |
| VCC     | **Fuente externa de 5V/6V** (los servos consumen picos de corriente) |
| GND     | GND común con el Raspberry |

⚠️ **Importante:** alimenta el motor y el servo con una fuente externa, no
directamente del Raspberry Pi. Los motores pueden causar caídas de voltaje
("brownouts") que reinician o cuelgan el Pi. Solo comparte tierra (GND)
entre la fuente externa y el Raspberry.

## 4. TLE offline (SGP4)

`tle_manager.py` intenta descargar los TLE de CelesTrak cada vez que
arranca el HMI. Si no hay internet:
1. Busca el último archivo guardado en `~/hmi_data/tle_cache.txt` (dentro
   de tu carpeta personal, según `RUTA_CACHE_TLE` en `config.py`).
2. Si existe, lo usa para calcular las órbitas con SGP4 (a través de
   Skyfield) aunque los datos ya no sean del día.
3. Si nunca se ha descargado nada (primer uso sin red), el HMI avisa en
   pantalla que no hay datos disponibles.

Recomendación: conecta el Raspberry a internet al menos una vez al día
(o cada pocos días) para mantener los TLE razonablemente actualizados;
los elementos orbitales se degradan con el tiempo.

## 5. Espectro SDR y trayectoria del pase

La pantalla "Espectro SDR" hace lo siguiente al presionar "con/sin efecto
Doppler":

1. Calcula la elevación actual del satélite. Si está bajo el horizonte,
   la gráfica solo muestra ruido y el HMI indica claramente
   **"el satélite no está pasando en este momento"**.
2. Si está sobre el horizonte, captura (o simula) el espectro alrededor de
   su frecuencia LRPT (137.900 MHz) y busca su portadora:
   - Si **no se detecta** señal (por ejemplo por una antena mal orientada
     o un pase muy bajo), lo indica en pantalla.
   - Si **sí se detecta**, muestra la frecuencia exacta, el SNR y el
     corrimiento Doppler, y habilita el botón **"Ver trayectoria del
     pase"**, que dibuja la traza en tierra y la gráfica polar
     Azimut/Elevación real del pase (con la posición actual marcada) para
     el rango en el que se encuentre el satélite en ese momento.

`spectro_sdr.py` usa un RTL-SDR real vía `pyrtlsdr` cuando hay uno
conectado. Si no hay hardware (por ejemplo al probar en una PC), entra en
"modo simulación": genera una señal realista basada en si el satélite
está realmente sobre el horizonte y en su velocidad radial real (para el
corrimiento Doppler), igual que `antenna_control.py` ya hace con el motor
y el servo.

## 6. Arranque automático al encender el Raspberry Pi

### Opción A (recomendada) — Autologin + autostart de escritorio
Usa esta opción si trabajas con Raspberry Pi OS con escritorio (LXDE/Wayfire).

1. Activa el autologin de tu usuario (sustituye `pi` por tu usuario real,
   por ejemplo `maxchqto`, si es distinto):
   ```bash
   sudo raspi-config
   # System Options -> Boot / Auto Login -> Desktop Autologin
   ```
2. Copia el archivo de autoarranque y edítalo con tu ruta real de usuario
   (reemplaza `TU_USUARIO` dentro del archivo por tu nombre de usuario):
   ```bash
   mkdir -p ~/.config/autostart
   cp ~/hmi_project/hmi-autostart.desktop ~/.config/autostart/
   nano ~/.config/autostart/hmi-autostart.desktop   # reemplaza TU_USUARIO
   ```
3. Desactiva el protector de pantalla y el apagado de pantalla (para que el
   HMI no se ponga en negro):
   ```bash
   sudo raspi-config
   # Display Options -> Screen Blanking -> No
   ```
4. Reinicia: `sudo reboot`. El HMI debería abrirse solo, en pantalla completa.

### Opción B — Servicio systemd (para Raspberry Pi OS Lite / kiosko)
Si no usas escritorio, usa `systemd` + `xinit`:

```bash
sudo nano /etc/systemd/system/hmi.service
```
```ini
[Unit]
Description=HMI METEOR-M
After=network-online.target
Wants=network-online.target

[Service]
User=TU_USUARIO
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/startx /usr/bin/python3 /home/TU_USUARIO/hmi_project/hmi_main.py -- -nocursor
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable hmi.service
sudo reboot
```
El `ExecStartPre=/bin/sleep 5` da tiempo a que la red se estabilice antes
de que el HMI intente descargar los TLE (si no hay red, de todos modos
usará la caché).

## 7. Notas y posibles mejoras

- El movimiento de motores corre en un hilo aparte (`threading`) para que
  la interfaz y los botones físicos no se congelen mientras el motor de
  pasos gira.
- Actualmente el apuntado calcula az/el para el instante en que se pulsa
  "Apuntar antena". Para **seguimiento continuo** durante un paso del
  satélite, se podría llamar `apuntar_antena()` cada 1-2 segundos con
  `root.after()` mientras el satélite esté sobre el horizonte.
- Las gráficas de trayectoria y el espectro SDR siguen como espacios
  reservados (igual que en el código original); se pueden integrar con
  `matplotlib` embebido en Tkinter (`FigureCanvasTkAgg`) y con `pyrtlsdr`
  para el receptor SDR real.
- Si vas a correr `hmi_main.py` en una laptop/PC sin Raspberry (para
  probar la lógica), no necesitas instalar `RPi.GPIO`/`gpiozero`: el
  código detecta que no hay hardware y entra en modo simulación (usa
  flechas y Enter del teclado, e imprime los movimientos de motor en
  consola en vez de moverlos).

# HMI NOAA para Raspberry Pi 4B

Proyecto listo para correr directamente en el Raspberry Pi: HMI en pantalla
completa, navegación con 3 botones físicos, descarga de TLE con respaldo
offline en caché, cálculo orbital con SGP4 (vía Skyfield) y movimiento de
un motor de pasos (azimut) + servo (elevación) para apuntar la antena.

## 1. Estructura del proyecto

```
hmi_project/
├── hmi_main.py          # Programa principal (ejecutar este)
├── config.py             # Pines GPIO, ubicación de la antena, URL de TLE
├── tle_manager.py         # Descarga TLE / respaldo en caché local
├── antenna_control.py     # Cálculo de az/el + control de motor y servo
├── gpio_buttons.py        # Lectura de los 3 botones físicos
├── requirements.txt
└── hmi-autostart.desktop  # Arranque automático
```

## 2. Instalación en el Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip python3-tk python3-rpi.gpio

# Copia la carpeta hmi_project a /home/pi/
cd /home/pi/hmi_project
pip3 install -r requirements.txt --break-system-packages
```

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
1. Busca el último archivo guardado en `/home/pi/hmi_data/tle_cache.txt`.
2. Si existe, lo usa para calcular las órbitas con SGP4 (a través de
   Skyfield) aunque los datos ya no sean del día.
3. Si nunca se ha descargado nada (primer uso sin red), el HMI avisa en
   pantalla que no hay datos disponibles.

Recomendación: conecta el Raspberry a internet al menos una vez al día
(o cada pocos días) para mantener los TLE razonablemente actualizados;
los elementos orbitales se degradan con el tiempo.

## 5. Arranque automático al encender el Raspberry Pi

### Opción A (recomendada) — Autologin + autostart de escritorio
Usa esta opción si trabajas con Raspberry Pi OS con escritorio (LXDE/Wayfire).

1. Activa el autologin del usuario `pi`:
   ```bash
   sudo raspi-config
   # System Options -> Boot / Auto Login -> Desktop Autologin
   ```
2. Copia el archivo de autoarranque:
   ```bash
   mkdir -p ~/.config/autostart
   cp /home/pi/hmi_project/hmi-autostart.desktop ~/.config/autostart/
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
Description=HMI NOAA
After=network-online.target
Wants=network-online.target

[Service]
User=pi
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/startx /usr/bin/python3 /home/pi/hmi_project/hmi_main.py -- -nocursor
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

## 6. Notas y posibles mejoras

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

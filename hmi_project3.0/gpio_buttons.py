"""
Botones físicos de navegación: ARRIBA, ENTER, ABAJO.

Usa gpiozero (con antirrebote integrado). Cada botón se conecta entre su
pin GPIO y GND; se usa la resistencia pull-up interna, así que no se
necesitan resistencias externas.

Si el módulo se ejecuta fuera de un Raspberry Pi (por ejemplo, para probar
el HMI en una PC), simplemente no hace nada aquí: en ese caso hmi_main.py
usa las teclas de flecha y Enter del teclado como respaldo.
"""
import config

try:
    from gpiozero import Button
    RASPBERRY = True
except ImportError:
    RASPBERRY = False


class BotonesFisicos:
    def __init__(self, callback_arriba, callback_enter, callback_abajo):
        self.disponible = RASPBERRY
        if not RASPBERRY:
            print("[Botones] gpiozero no disponible: usa ↑ / Enter / ↓ del teclado como respaldo.")
            return

        self.btn_arriba = Button(config.PIN_BOTON_ARRIBA, pull_up=True, bounce_time=0.05)
        self.btn_enter = Button(config.PIN_BOTON_ENTER, pull_up=True, bounce_time=0.05)
        self.btn_abajo = Button(config.PIN_BOTON_ABAJO, pull_up=True, bounce_time=0.05)

        # OJO: estos callbacks se ejecutan en un hilo de gpiozero, NO en el hilo
        # principal de Tkinter. Por eso en hmi_main.py siempre se agenda el
        # trabajo real con root.after(0, ...) dentro de estos callbacks.
        self.btn_arriba.when_pressed = callback_arriba
        self.btn_enter.when_pressed = callback_enter
        self.btn_abajo.when_pressed = callback_abajo

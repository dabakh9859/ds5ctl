"""Lit la DualSense via evdev et expose un périphérique virtuel (uinput) :
un volant Logitech G29 (reconnu nativement par BeamNG et la plupart des jeux de course)
ou une manette Xbox 360. L'inclinaison de la manette pilote la direction, avec un
angle total réglable comme dans DS4Windows.
"""
import glob
import math
import os
import select
import threading
import time

import evdev
from evdev import ecodes as e

GYRO_RES = 1024.0     # unités par °/s (hid-playstation)
ACCEL_RES = 8192.0    # unités par g
PS_HOLD_TOGGLE = 0.6  # appui long sur PS (s) : active/désactive le gyro


class XboxOutput:
    """Manette Xbox 360 : la direction va sur le stick gauche X."""

    # Carré = X Xbox (BTN_X, 307), Triangle = Y Xbox (BTN_Y, 308).
    BUTTONS = {
        e.BTN_SOUTH: e.BTN_A, e.BTN_EAST: e.BTN_B, e.BTN_WEST: e.BTN_X, e.BTN_NORTH: e.BTN_Y,
        e.BTN_TL: e.BTN_TL, e.BTN_TR: e.BTN_TR, e.BTN_SELECT: e.BTN_SELECT, e.BTN_START: e.BTN_START,
        e.BTN_MODE: e.BTN_MODE, e.BTN_THUMBL: e.BTN_THUMBL, e.BTN_THUMBR: e.BTN_THUMBR,
    }

    def __init__(self):
        stick = evdev.AbsInfo(0, -32768, 32767, 16, 128, 0)
        trig = evdev.AbsInfo(0, 0, 255, 0, 0, 0)
        hat = evdev.AbsInfo(0, -1, 1, 0, 0, 0)
        caps = {
            e.EV_KEY: sorted(set(self.BUTTONS.values())),
            e.EV_ABS: [(e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_RX, stick), (e.ABS_RY, stick),
                       (e.ABS_Z, trig), (e.ABS_RZ, trig), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
        }
        self.ui = evdev.UInput(caps, name="Microsoft X-Box 360 pad", vendor=0x045E,
                               product=0x028E, version=0x110, bustype=e.BUS_USB)

    def button(self, code, value):
        if code in self.BUTTONS:
            self.ui.write(e.EV_KEY, self.BUTTONS[code], value)

    def axis(self, code, value):
        if code in (e.ABS_Y, e.ABS_RX, e.ABS_RY):
            self.ui.write(e.EV_ABS, code, _stick(value))
        elif code in (e.ABS_Z, e.ABS_RZ, e.ABS_HAT0X, e.ABS_HAT0Y):
            self.ui.write(e.EV_ABS, code, value)

    def steer(self, x):
        self.ui.write(e.EV_ABS, e.ABS_X, int(round(x * 32767)))

    def reset(self):
        for code in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY, e.ABS_Z, e.ABS_RZ, e.ABS_HAT0X, e.ABS_HAT0Y):
            self.ui.write(e.EV_ABS, code, 0)
        for code in set(self.BUTTONS.values()):
            self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def syn(self):
        self.ui.syn()

    def close(self):
        self.ui.close()


class WheelOutput:
    """Volant Logitech G29 : axes et boutons alignés sur le profil G29 de BeamNG
    (xaxis = direction, yaxis = accélérateur, rzaxis = frein, slider = embrayage,
    bouton 4/5 = palettes)."""

    # index des boutons comme les voit le jeu (ordre des codes evdev)
    CODES = list(range(e.BTN_TRIGGER, e.BTN_DEAD + 1)) + list(range(e.BTN_TRIGGER_HAPPY1, e.BTN_TRIGGER_HAPPY1 + 9))
    BUTTONS = {
        e.BTN_SOUTH: 0,    # Croix : valider / frein à main
        e.BTN_WEST: 1,     # Carré : clignotant gauche
        e.BTN_EAST: 2,     # Rond : retour / clignotant droit
        e.BTN_NORTH: 3,    # Triangle
        e.BTN_TR: 4,       # R1 : vitesse +
        e.BTN_TL: 5,       # L1 : vitesse -
        e.BTN_SELECT: 7,   # Créer : regarder derrière
        e.BTN_START: 9,    # Options : menus
        e.BTN_THUMBL: 10,  # L3 : caméra suivante
        e.BTN_THUMBR: 11,  # R3 : recentrer la caméra
        e.BTN_MODE: 24,    # PS (si non utilisé pour recentrer) : pause
    }
    PEDAL = evdev.AbsInfo(65535, 0, 65535, 0, 0, 0)

    def __init__(self):
        axis = evdev.AbsInfo(32768, 0, 65535, 0, 0, 0)
        hat = evdev.AbsInfo(0, -1, 1, 0, 0, 0)
        caps = {
            e.EV_KEY: self.CODES,
            e.EV_ABS: [(e.ABS_X, axis), (e.ABS_Y, self.PEDAL), (e.ABS_Z, self.PEDAL),
                       (e.ABS_RX, axis), (e.ABS_RY, axis), (e.ABS_RZ, self.PEDAL),
                       (e.ABS_THROTTLE, self.PEDAL), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
        }
        self.ui = evdev.UInput(caps, name="Logitech G29 Driving Force Racing Wheel", vendor=0x046D,
                               product=0xC24F, version=0x111, bustype=e.BUS_USB)

    def button(self, code, value):
        if code in self.BUTTONS:
            self.ui.write(e.EV_KEY, self.CODES[self.BUTTONS[code]], value)

    def axis(self, code, value):
        if code == e.ABS_RZ:      # R2 -> accélérateur (pédale relâchée = 65535)
            self.ui.write(e.EV_ABS, e.ABS_Y, 65535 - value * 257)
        elif code == e.ABS_Z:     # L2 -> frein
            self.ui.write(e.EV_ABS, e.ABS_RZ, 65535 - value * 257)
        elif code in (e.ABS_RX, e.ABS_RY):  # stick droit, libre à assigner (caméra…)
            self.ui.write(e.EV_ABS, code, value * 257)
        elif code in (e.ABS_HAT0X, e.ABS_HAT0Y):
            self.ui.write(e.EV_ABS, code, value)

    def steer(self, x):
        self.ui.write(e.EV_ABS, e.ABS_X, int(round(32767.5 + x * 32767.5)))

    def reset(self):
        for code in (e.ABS_Y, e.ABS_Z, e.ABS_RZ, e.ABS_THROTTLE):
            self.ui.write(e.EV_ABS, code, 65535)
        for code in (e.ABS_X, e.ABS_RX, e.ABS_RY):
            self.ui.write(e.EV_ABS, code, 32768)
        for code in (e.ABS_HAT0X, e.ABS_HAT0Y):
            self.ui.write(e.EV_ABS, code, 0)
        for code in self.CODES:
            self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()

    def syn(self):
        self.ui.syn()

    def close(self):
        self.ui.close()


class WheelPadOutput:
    """Volant G29 pour la direction et les pédales + manette Xbox pour tout le reste :
    le jeu garde ses commandes manette habituelles (boutons, caméra, croix directionnelle)."""

    def __init__(self):
        self.wheel = WheelOutput()
        self.pad = XboxOutput()

    def button(self, code, value):
        self.pad.button(code, value)

    def axis(self, code, value):
        if code in (e.ABS_Z, e.ABS_RZ):      # gâchettes -> pédales du volant
            self.wheel.axis(code, value)
        else:                                # stick gauche Y, stick droit, croix
            self.pad.axis(code, value)

    def steer(self, x):
        self.wheel.steer(x)

    def reset(self):
        self.wheel.reset()
        self.pad.reset()

    def syn(self):
        self.wheel.syn()
        self.pad.syn()

    def close(self):
        self.wheel.close()
        self.pad.close()


OUTPUTS = {"wheel": WheelPadOutput, "wheel_only": WheelOutput, "xbox": XboxOutput}


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _unit(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _stick(v):
    return max(-32768, min(32767, int(round((v - 128) * 257.0))))


def find_dualsense():
    """Renvoie (périphérique principal, capteurs de mouvement) ou (None, None)."""
    main = motion = None
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        if d.info.vendor != 0x054C or "DualSense" not in d.name:
            d.close()
            continue
        if d.name.endswith("Motion Sensors"):
            motion = d
        elif d.name.endswith("Controller"):
            main = d
        else:
            d.close()
    if main and motion:
        return main, motion
    for d in (main, motion):
        if d:
            d.close()
    return None, None


def battery_level():
    for cap in glob.glob("/sys/class/power_supply/ps-controller-battery-*/capacity"):
        try:
            status = open(os.path.join(os.path.dirname(cap), "status")).read().strip()
            return int(open(cap).read()), status
        except (OSError, ValueError):
            pass
    return None, None


class Engine(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self._quit = threading.Event()
        self._recenter = threading.Event()
        self.connected = False
        self.error = None
        self.angle = 0.0      # inclinaison par rapport au centre (°)
        self.output = 0.0     # direction envoyée au jeu, -1..1
        self.throttle = 0.0   # accélérateur envoyé (R2), 0..1
        self.brake = 0.0      # frein envoyé (L2), 0..1
        self.out = None

    # --- réglages ---------------------------------------------------------
    @property
    def profile(self):
        return self.cfg["profiles"][self.cfg["active_profile"]]

    def recenter(self):
        self._recenter.set()

    def stop(self):
        self._quit.set()

    # --- boucle -----------------------------------------------------------
    def run(self):
        try:
            self.out = OUTPUTS[self.cfg.get("device", "wheel")]()
            self.out.reset()
        except OSError as exc:
            self.error = f"uinput indisponible : {exc}"
            return
        try:
            while not self._quit.is_set():
                main, motion = find_dualsense()
                if not main:
                    self.connected = False
                    self._quit.wait(1.0)
                    continue
                try:
                    self._session(main, motion)
                except OSError:
                    pass  # manette déconnectée
                finally:
                    self.connected = False
                    for d in (main, motion):
                        try:
                            d.ungrab()
                        except OSError:
                            pass
                        d.close()
                    self.out.reset()
                    self.output = 0.0
        finally:
            self.out.close()

    def _session(self, main, motion):
        if self.cfg.get("hide_physical", True):
            try:
                main.grab()
            except OSError:
                pass
        self.connected = True

        acc = {c: motion.absinfo(c).value for c in (e.ABS_X, e.ABS_Y, e.ABS_Z, e.ABS_RX, e.ABS_RY, e.ABS_RZ)}
        stick_x = main.absinfo(e.ABS_X).value
        theta = theta0 = 0.0         # angle fusionné (non replié) et centre
        axis = u = v = (0.0, 0.0, 1.0)  # axe du volant et repère du plan de rotation
        gyro_sign = 1.0              # sens du gyro, confirmé par vote accéléro/gyro
        votes = [0, 0]
        prev_acc_angle = None
        bias = [0.0, 0.0, 0.0]
        last_ts = None
        smoothed = 0.0
        ps_down_at = None

        def gravity():
            return (acc[e.ABS_X] / ACCEL_RES, acc[e.ABS_Y] / ACCEL_RES, acc[e.ABS_Z] / ACCEL_RES)

        def accel_angle():
            g = gravity()
            ga, gb = _dot(g, u), _dot(g, v)
            return -math.degrees(math.atan2(gb, ga)), math.hypot(ga, gb), math.sqrt(_dot(g, g))

        def do_recenter():
            # L'axe du volant est horizontal et perpendiculaire à l'axe gauche-droite de la
            # manette : ça marche qu'elle soit tenue à plat, inclinée ou verticale.
            nonlocal theta, theta0, axis, u, v, prev_acc_angle, smoothed, votes
            g0 = _unit(gravity())
            n = (0.0, -g0[2], g0[1])  # X_manette × gravité
            axis = _unit(n) if _dot(n, n) > 0.05 else (0.0, 1.0, 0.0)
            u = _unit(_sub(g0, _scale(axis, _dot(g0, axis))))
            v = _cross(axis, u)
            a, _, _ = accel_angle()
            theta = theta0 = a
            prev_acc_angle = a
            smoothed = 0.0
            votes = [0, 0]

        do_recenter()
        fds = {main.fd: main, motion.fd: motion}
        while not self._quit.is_set():
            p = self.profile
            if self._recenter.is_set():
                self._recenter.clear()
                do_recenter()

            ready, _, _ = select.select(list(fds), [], [], 0.25)
            for fd in ready:
                dev = fds[fd]
                for ev in dev.read():
                    if dev is motion:
                        if ev.type == e.EV_ABS:
                            acc[ev.code] = ev.value
                        elif ev.type == e.EV_MSC and ev.code == e.MSC_TIMESTAMP:
                            ts = ev.value
                            dt = ((ts - last_ts) & 0xFFFFFFFF) / 1e6 if last_ts is not None else 0.004
                            last_ts = ts
                            if not 0 < dt < 0.1:
                                dt = 0.004
                        elif ev.type == e.EV_SYN:
                            # --- fusion gyro + accéléromètre ---
                            w = [acc[c] / GYRO_RES for c in (e.ABS_RX, e.ABS_RY, e.ABS_RZ)]
                            if all(abs(w[i] - bias[i]) < 2.0 for i in range(3)):  # immobile : suit la dérive
                                for i in range(3):
                                    bias[i] += 0.002 * (w[i] - bias[i])
                            rate = _dot([w[i] - bias[i] for i in range(3)], axis)
                            a, plane, norm = accel_angle()
                            reliable = abs(norm - 1.0) < 0.15 and plane > 0.5
                            if reliable and prev_acc_angle is not None and abs(rate) > 30:
                                acc_rate = _wrap(a - prev_acc_angle) / dt
                                if abs(acc_rate) > 30:
                                    votes[0 if acc_rate * rate * gyro_sign > 0 else 1] += 1
                                    if votes[1] > 40 and votes[1] > 3 * votes[0]:
                                        gyro_sign = -gyro_sign
                                        votes = [0, 0]
                            prev_acc_angle = a
                            theta += gyro_sign * rate * dt
                            if reliable:
                                theta += 0.01 * _wrap(a - theta)
                            self.angle = theta0 - theta  # positif = droite
                            out = self._shape(self.angle, p) if p["gyro_enabled"] else 0.0
                            smoothed += (1.0 - min(p["smoothing"], 0.95)) * (out - smoothed)
                            self._emit_steer(smoothed, stick_x, p)
                        continue

                    # --- périphérique principal ---
                    if ev.type == e.EV_KEY and ev.code == e.BTN_MODE and self.cfg.get("ps_recenters", True):
                        if ev.value == 1:
                            ps_down_at = time.monotonic()
                        elif ev.value == 0 and ps_down_at is not None:
                            if time.monotonic() - ps_down_at >= PS_HOLD_TOGGLE:
                                p["gyro_enabled"] = not p["gyro_enabled"]
                            else:
                                do_recenter()
                            ps_down_at = None
                        continue
                    if ev.type == e.EV_KEY:
                        self.out.button(ev.code, ev.value)
                    elif ev.type == e.EV_ABS:
                        if ev.code == e.ABS_X:
                            stick_x = ev.value
                            self._emit_steer(smoothed if p["gyro_enabled"] else 0.0, stick_x, p)
                        else:
                            if ev.code == e.ABS_RZ:
                                self.throttle = self._pedal(ev.value, p, "throttle")
                                self.out.axis(ev.code, int(round(self.throttle * 255)))
                            elif ev.code == e.ABS_Z:
                                self.brake = self._pedal(ev.value, p, "brake")
                                self.out.axis(ev.code, int(round(self.brake * 255)))
                            else:
                                self.out.axis(ev.code, ev.value)
                    elif ev.type == e.EV_SYN:
                        self.out.syn()

    @staticmethod
    def _pedal(raw, p, name):
        t = raw / 255.0
        dz = p[name + "_deadzone"]
        top = max(p[name + "_max"], dz + 0.05)
        if t <= dz:
            return 0.0
        t = min((t - dz) / (top - dz), 1.0)
        return t ** max(p[name + "_curve"], 0.1)

    @staticmethod
    def _shape(angle, p):
        half = max(p["range"], 10) / 2.0
        x = angle / half
        if p["invert"]:
            x = -x
        mag = min(abs(x), 1.0)
        dz = p["deadzone"]
        mag = 0.0 if mag <= dz else (mag - dz) / (1.0 - dz)
        mag **= max(p["curve"], 0.1)
        return math.copysign(mag, x)

    def _emit_steer(self, gyro_out, stick_raw, p):
        stick = (stick_raw - 128) / 127.0
        if abs(stick) < 0.06:
            stick = 0.0
        x = gyro_out + (stick if (p["mix_stick"] or not p["gyro_enabled"]) else 0.0)
        x = max(-1.0, min(1.0, x))
        self.output = x
        self.out.steer(x)
        self.out.syn()

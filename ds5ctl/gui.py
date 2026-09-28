import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import APP_ID, config  # noqa: E402
from .config import DEFAULT_PROFILE  # noqa: E402
from .engine import Engine, battery_level  # noqa: E402

DEVICES = (("wheel", "Volant Logitech G29 (BeamNG, jeux de course)"), ("xbox", "Manette Xbox 360"))
PRESETS = (90, 180, 270, 360, 540, 720, 900, 1080)


class SteeringView(Gtk.DrawingArea):
    """Volant qui tourne avec l'inclinaison + barre de sortie du stick."""

    def __init__(self):
        super().__init__()
        self.angle = 0.0
        self.output = 0.0
        self.set_content_height(170)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def update(self, angle, output):
        if abs(angle - self.angle) > 0.2 or abs(output - self.output) > 0.002:
            self.angle, self.output = angle, output
            self.queue_draw()

    def _draw(self, _area, cr, w, h):
        fg = self.get_color()
        accent = (0.36, 0.55, 0.95)
        cx, cy, r = w / 2, 68, 52
        # volant
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(math.radians(self.angle))
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.85)
        cr.set_line_width(9)
        cr.arc(0, 0, r, 0, 2 * math.pi)
        cr.stroke()
        cr.set_line_width(7)
        for a in (math.pi, 0, math.pi / 2):
            cr.move_to(0, 0)
            cr.line_to(r * math.cos(a), r * math.sin(a))
            cr.stroke()
        cr.set_source_rgb(*accent)
        cr.set_line_width(9)
        cr.arc(0, 0, r, -math.pi / 2 - 0.25, -math.pi / 2 + 0.25)
        cr.stroke()
        cr.restore()
        # barre de sortie
        bw, by, bh = min(w - 40, 420), 138, 12
        bx = (w - bw) / 2
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
        cr.rectangle(bx, by, bw, bh)
        cr.fill()
        cr.set_source_rgb(*accent)
        mid = bx + bw / 2
        cr.rectangle(min(mid, mid + self.output * bw / 2), by, abs(self.output) * bw / 2, bh)
        cr.fill()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
        cr.rectangle(mid - 1, by - 3, 2, bh + 6)
        cr.fill()
        # texte
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.8)
        cr.select_font_face("sans")
        cr.set_font_size(12)
        txt = f"{self.angle:+.0f}°   ·   direction {self.output * 100:+.0f} %"
        ext = cr.text_extents(txt)
        cr.move_to((w - ext.width) / 2, by + bh + 16)
        cr.show_text(txt)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DS5 Control")
        self.set_default_size(560, 860)
        self.cfg = config.load()
        self.engine = None
        self._save_id = 0
        self._loading = False

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        self.set_content(toolbar)

        # --- état ---
        g = Adw.PreferencesGroup(title="Manette")
        self.status_row = Adw.ActionRow(title="DualSense", subtitle="Recherche…")
        self.status_icon = Gtk.Image(icon_name="input-gaming-symbolic")
        self.status_row.add_prefix(self.status_icon)
        g.add(self.status_row)
        self.run_row = Adw.SwitchRow(title="Manette virtuelle active",
                                     subtitle="Crée le périphérique que voient les jeux")
        self.run_row.connect("notify::active", self._on_run)
        g.add(self.run_row)
        self.device_row = Adw.ComboRow(title="Émuler", model=Gtk.StringList.new([d[1] for d in DEVICES]))
        self.device_row.connect("notify::selected", self._on_device)
        g.add(self.device_row)
        page.add(g)

        # --- aperçu ---
        g = Adw.PreferencesGroup(title="Volant",
                                 description="PS : recentrer · PS maintenu : activer/désactiver le gyro")
        self.view = SteeringView()
        frame = Gtk.Frame(child=self.view)
        frame.add_css_class("view")
        g.add(frame)
        btn = Gtk.Button(label="Recentrer", halign=Gtk.Align.CENTER, margin_top=10)
        btn.add_css_class("pill")
        btn.connect("clicked", lambda *_: self.engine and self.engine.recenter())
        g.add(btn)
        page.add(g)

        # --- profil ---
        g = Adw.PreferencesGroup(title="Profil")
        self.profile_model = Gtk.StringList()
        self.profile_row = Adw.ComboRow(title="Profil actif", model=self.profile_model)
        self.profile_row.connect("notify::selected", self._on_profile_selected)
        g.add(self.profile_row)
        self.new_row = Adw.EntryRow(title="Nouveau profil (nom puis Entrée)")
        self.new_row.set_show_apply_button(True)
        self.new_row.connect("apply", self._on_new_profile)
        g.add(self.new_row)
        del_row = Adw.ActionRow(title="Supprimer le profil actif")
        del_btn = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        del_btn.add_css_class("flat")
        del_btn.connect("clicked", self._on_delete_profile)
        del_row.add_suffix(del_btn)
        g.add(del_row)
        page.add(g)

        # --- gyro ---
        g = Adw.PreferencesGroup(title="Gyro → direction")
        self.gyro_row = Adw.SwitchRow(title="Gyro volant")
        self.gyro_row.connect("notify::active", lambda r, _: self._set("gyro_enabled", r.get_active()))
        g.add(self.gyro_row)

        range_row = Adw.ActionRow(title="Angle de braquage total",
                                  subtitle="Inclinaison de butée à butée")
        self.range_scale = self._scale(90, 1080, 10, 0, lambda v: self._set("range", int(v)))
        self.range_scale.set_format_value_func(lambda _s, v: f"{v:.0f}°")
        range_row.add_suffix(self.range_scale)
        g.add(range_row)

        presets = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8,
                              min_children_per_line=4, margin_top=8, margin_bottom=4,
                              column_spacing=6, row_spacing=6, homogeneous=True)
        for deg in PRESETS:
            b = Gtk.Button(label=f"{deg}°")
            b.connect("clicked", lambda _b, d=deg: self.range_scale.set_value(d))
            presets.append(b)
        g.add(presets)

        dz_row = Adw.ActionRow(title="Zone morte")
        self.dz_scale = self._scale(0, 30, 1, 0, lambda v: self._set("deadzone", v / 100))
        self.dz_scale.set_format_value_func(lambda _s, v: f"{v:.0f} %")
        dz_row.add_suffix(self.dz_scale)
        g.add(dz_row)

        curve_row = Adw.ActionRow(title="Courbe", subtitle="1 = linéaire · plus haut = plus doux au centre")
        self.curve_scale = self._scale(0.5, 3.0, 0.1, 1, lambda v: self._set("curve", round(v, 2)))
        curve_row.add_suffix(self.curve_scale)
        g.add(curve_row)

        smooth_row = Adw.ActionRow(title="Lissage")
        self.smooth_scale = self._scale(0, 90, 5, 0, lambda v: self._set("smoothing", v / 100))
        self.smooth_scale.set_format_value_func(lambda _s, v: f"{v:.0f} %")
        smooth_row.add_suffix(self.smooth_scale)
        g.add(smooth_row)

        self.invert_row = Adw.SwitchRow(title="Inverser la direction")
        self.invert_row.connect("notify::active", lambda r, _: self._set("invert", r.get_active()))
        g.add(self.invert_row)
        self.mix_row = Adw.SwitchRow(title="Garder le stick gauche",
                                     subtitle="Le stick gauche s'ajoute au gyro pour diriger")
        self.mix_row.connect("notify::active", lambda r, _: self._set("mix_stick", r.get_active()))
        g.add(self.mix_row)
        page.add(g)

        # --- options ---
        g = Adw.PreferencesGroup(title="Options")
        self.hide_row = Adw.SwitchRow(title="Masquer la vraie DualSense aux jeux",
                                      subtitle="Évite que les jeux voient deux manettes")
        self.hide_row.connect("notify::active", self._on_hide)
        g.add(self.hide_row)
        self.ps_row = Adw.SwitchRow(title="Bouton PS = recentrer",
                                    subtitle="Sinon il est transmis au jeu (bouton Guide)")
        self.ps_row.connect("notify::active", lambda r, _: self._set_global("ps_recenters", r.get_active()))
        g.add(self.ps_row)
        page.add(g)

        self._load_profiles()
        self.run_row.set_active(True)
        GLib.timeout_add(33, self._tick)
        self.connect("close-request", self._on_close)

    # --- helpers ---
    def _scale(self, lo, hi, step, digits, cb):
        s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        s.set_digits(digits)
        s.set_draw_value(True)
        s.set_value_pos(Gtk.PositionType.LEFT)
        s.set_size_request(230, -1)
        s.set_valign(Gtk.Align.CENTER)
        s.connect("value-changed", lambda w: None if self._loading else cb(w.get_value()))
        return s

    @property
    def profile(self):
        return self.cfg["profiles"][self.cfg["active_profile"]]

    def _set(self, key, value):
        if self._loading:
            return
        self.profile[key] = value
        self._queue_save()

    def _set_global(self, key, value):
        if self._loading:
            return
        self.cfg[key] = value
        self._queue_save()

    def _queue_save(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(400, self._save)

    def _save(self):
        self._save_id = 0
        config.save(self.cfg)
        return False

    def _load_profiles(self):
        self._loading = True
        names = list(self.cfg["profiles"])
        self.profile_model.splice(0, self.profile_model.get_n_items(), names)
        self.profile_row.set_selected(names.index(self.cfg["active_profile"]))
        self._loading = False
        self._load_values()

    def _load_values(self):
        self._loading = True
        p = self.profile
        self.gyro_row.set_active(p["gyro_enabled"])
        self.range_scale.set_value(p["range"])
        self.dz_scale.set_value(p["deadzone"] * 100)
        self.curve_scale.set_value(p["curve"])
        self.smooth_scale.set_value(p["smoothing"] * 100)
        self.invert_row.set_active(p["invert"])
        self.mix_row.set_active(p["mix_stick"])
        self.hide_row.set_active(self.cfg["hide_physical"])
        self.device_row.set_selected([d[0] for d in DEVICES].index(self.cfg["device"]))
        self.ps_row.set_active(self.cfg["ps_recenters"])
        self._loading = False

    # --- callbacks ---
    def _on_profile_selected(self, row, _):
        if self._loading:
            return
        names = list(self.cfg["profiles"])
        self.cfg["active_profile"] = names[row.get_selected()]
        self._load_values()
        self._queue_save()

    def _on_new_profile(self, row):
        name = row.get_text().strip()
        if not name or name in self.cfg["profiles"]:
            return
        self.cfg["profiles"][name] = dict(self.profile) if self.profile else dict(DEFAULT_PROFILE)
        self.cfg["active_profile"] = name
        row.set_text("")
        self._load_profiles()
        self._queue_save()

    def _on_delete_profile(self, _btn):
        if len(self.cfg["profiles"]) <= 1:
            return
        del self.cfg["profiles"][self.cfg["active_profile"]]
        self.cfg["active_profile"] = next(iter(self.cfg["profiles"]))
        self._load_profiles()
        self._queue_save()

    def _on_run(self, row, _):
        if row.get_active():
            self._start_engine()
        else:
            self._stop_engine()

    def _on_hide(self, row, _):
        self._set_global("hide_physical", row.get_active())
        self._restart_engine()

    def _on_device(self, row, _):
        self._set_global("device", DEVICES[row.get_selected()][0])
        self._restart_engine()

    def _restart_engine(self):
        if not self._loading and self.engine:
            self._stop_engine()
            self._start_engine()

    def _start_engine(self):
        if not self.engine:
            self.engine = Engine(self.cfg)
            self.engine.start()

    def _stop_engine(self):
        if self.engine:
            self.engine.stop()
            self.engine.join(2)
            self.engine = None

    def _tick(self):
        eng = self.engine
        if eng and eng.error:
            self.status_row.set_subtitle(eng.error)
        elif eng and eng.connected:
            level, status = battery_level()
            bat = f" · batterie {level} %" + (" (en charge)" if status == "Charging" else "") if level is not None else ""
            self.status_row.set_subtitle("Connectée" + bat)
            self.view.update(eng.angle, eng.output)
        elif eng:
            self.status_row.set_subtitle("Non détectée — branche ou appaire la manette")
        else:
            self.status_row.set_subtitle("Manette virtuelle arrêtée")
        # le PS maintenu peut changer le gyro depuis la manette
        if self.gyro_row.get_active() != self.profile["gyro_enabled"]:
            self._loading = True
            self.gyro_row.set_active(self.profile["gyro_enabled"])
            self._loading = False
            self._queue_save()
        return True

    def _on_close(self, *_):
        self._stop_engine()
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save()
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.present()


def main():
    return App().run(None)

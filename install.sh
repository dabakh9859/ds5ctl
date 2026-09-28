#!/usr/bin/env bash
# Installe DS5 Control pour l'utilisateur courant.
#   ./install.sh              installer / mettre à jour
#   ./install.sh --uninstall  désinstaller
# Les étapes système (paquets, règle udev, module uinput) passent par sudo
# (ou la commande définie dans $SUDO, ex. SUDO=pkexec).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.ds5ctl"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
LIB_DIR="$DATA_HOME/ds5ctl"
BIN="$HOME/.local/bin/ds5ctl"
DESKTOP="$DATA_HOME/applications/$APP_ID.desktop"
ICON="$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
RULE="/etc/udev/rules.d/70-ds5ctl.rules"
MODLOAD="/etc/modules-load.d/ds5ctl.conf"
SUDO="${SUDO:-sudo}"

say() { printf '\033[1;34m::\033[0m %s\n' "$*"; }

refresh_desktop() {
  command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA_HOME/applications" || true
  command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  say "Désinstallation de DS5 Control"
  rm -rf "$LIB_DIR" "$BIN" "$DESKTOP" "$ICON"
  refresh_desktop
  $SUDO sh -c "rm -f '$RULE' '$MODLOAD' && udevadm control --reload"
  say "Terminé (la configuration reste dans ~/.config/ds5ctl)."
  exit 0
fi

# --- dépendances -----------------------------------------------------------
if command -v pacman >/dev/null; then
  PKGS="python python-evdev python-gobject gtk4 libadwaita"
  INSTALL="pacman -S --needed --noconfirm $PKGS"
elif command -v apt-get >/dev/null; then
  PKGS="python3 python3-evdev python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
  INSTALL="apt-get install -y $PKGS"
elif command -v dnf >/dev/null; then
  PKGS="python3 python3-evdev python3-gobject gtk4 libadwaita"
  INSTALL="dnf install -y $PKGS"
elif command -v zypper >/dev/null; then
  PKGS="python3 python3-evdev python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"
  INSTALL="zypper install -y $PKGS"
else
  INSTALL=""
  say "Distribution non reconnue : installe toi-même python-evdev, PyGObject, GTK 4 et libadwaita."
fi

# --- étapes système (une seule élévation) ---------------------------------
say "Configuration système : dépendances, règle udev, module uinput"
$SUDO sh -c "
  set -e
  ${INSTALL:+$INSTALL}
  install -Dm644 '$SRC/data/70-ds5ctl.rules' '$RULE'
  echo uinput > '$MODLOAD'
  modprobe uinput || true
  udevadm control --reload
  udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change
"

# --- application (utilisateur) -------------------------------------------
say "Installation de l'application dans $LIB_DIR"
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR" "$(dirname "$BIN")"
cp -r "$SRC/ds5ctl" "$LIB_DIR/"
find "$LIB_DIR" -name __pycache__ -prune -exec rm -rf {} +

cat > "$BIN" <<EOF
#!/bin/sh
PYTHONPATH="$LIB_DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m ds5ctl "\$@"
EOF
chmod +x "$BIN"

install -Dm644 "$SRC/data/$APP_ID.svg" "$ICON"
install -Dm644 "$SRC/data/$APP_ID.desktop" "$DESKTOP"
sed -i "s|^Exec=.*|Exec=$BIN|" "$DESKTOP"
refresh_desktop

python3 -c "import evdev, gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')" \
  || { echo "Dépendances Python manquantes (voir plus haut)." >&2; exit 1; }

say "DS5 Control est installé : cherche « DS5 Control » dans tes applications, ou lance « ds5ctl »."
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) say "Ajoute ~/.local/bin à ton PATH pour utiliser la commande ds5ctl." ;; esac
say "Si la manette était déjà branchée, débranche/rebranche-la une fois."

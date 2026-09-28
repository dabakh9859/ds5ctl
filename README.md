# DS5 Control

Utilise le **gyroscope de la manette PS5 (DualSense)** comme **volant** sous Linux, sans Wine ni Steam Input : l'alternative Linux au « Steering Wheel Emulation » de DS4Windows.

DS5 Control lit la DualSense et crée un périphérique virtuel que les jeux voient comme une vraie manette :

- **Volant G29 + boutons manette** (par défaut) : un volant Logitech G29 (reconnu nativement par BeamNG.drive et la plupart des jeux de course) reçoit la direction et les pédales, sans l'assistance « manette » qui bride la direction. Une manette Xbox virtuelle reçoit les boutons, le stick droit et la croix directionnelle, donc le jeu garde ses commandes manette habituelles.
- **Volant G29 seul** : tous les boutons passent par le volant, avec le profil G29 du jeu.
- **Manette Xbox 360** : pour tous les autres jeux. L'inclinaison pilote alors le stick gauche.

## Fonctionnalités

- Angle de braquage réglable de **90° à 1080°** (préréglages 90, 180, 270, 360, 540, 720, 900 et 1080°).
- Marche quelle que soit la tenue (à plat, inclinée ou verticale) : l'axe du volant est détecté au recentrage.
- Fusion gyroscope + accéléromètre : réactif, sans dérive.
- Zone morte, courbe de réponse, lissage et inversion.
- Le stick gauche peut s'ajouter au gyro.
- Profils (ex. un par jeu).
- **PS** : recentrer. **PS maintenu** : activer ou désactiver le gyro.
- Masque la vraie DualSense aux jeux, pour éviter les doublons.
- Affiche la batterie de la manette.
- USB et Bluetooth, DualSense et DualSense Edge.

### Correspondance en mode « Volant G29 seul » (profil G29 de BeamNG)

En mode « Volant G29 + boutons manette », seuls l'inclinaison et R2/L2 vont au volant ; tous les autres boutons gardent les commandes manette du jeu.

| DualSense | Volant G29 |
|---|---|
| Inclinaison | Volant |
| R2 / L2 | Accélérateur / frein |
| R1 / L1 | Vitesse + / − (palettes) |
| Croix | Valider / frein à main |
| Carré / Rond | Clignotant gauche / droit |
| Options | Menus |
| Créer | Regarder derrière |
| L3 / R3 | Caméra suivante / recentrer la caméra |
| Stick droit | Axes RX/RY libres (caméra…) |
| Croix directionnelle | Croix directionnelle |

## Installation

```sh
git clone https://github.com/dabakh9859/ds5ctl.git
cd ds5ctl
./install.sh
```

Le script gère Arch, Debian/Ubuntu, Fedora et openSUSE. Il installe les dépendances (python-evdev, PyGObject, GTK 4, libadwaita) et une règle udev qui donne à l'utilisateur l'accès aux capteurs de la manette et à `/dev/uinput`. L'application elle-même s'installe dans ton dossier personnel.

Désinstaller : `./install.sh --uninstall`

## Utilisation

Lance **DS5 Control** depuis tes applications, ou `ds5ctl` dans un terminal. Sans interface :

```sh
ds5ctl --headless --profile BeamNG
```

1. Branche ou appaire la DualSense : l'état passe à « Connectée ».
2. Tiens la manette en position neutre et appuie sur **PS** pour recentrer.
3. Règle l'angle : plus il est petit, moins il faut incliner pour braquer à fond.

### Avec Steam

Désactive Steam Input pour le jeu (Propriétés → Manette → Désactiver Steam Input). Sinon Steam crée ses propres manettes virtuelles par-dessus celle de DS5 Control.

Pour que le jeu ignore la DualSense et les manettes virtuelles de Steam, ajoute ces options de lancement :

```
SDL_JOYSTICK_HIDAPI=0 SDL_GAMECONTROLLER_IGNORE_DEVICES=0x054c/0x0ce6,0x28de/0x11ff %command%
```

### BeamNG.drive

- Le volant apparaît comme « Logitech G29 » dans Options → Controls, avec le profil G29 de BeamNG.
- Ce profil suppose un volant de 900°. L'angle réglé dans DS5 Control correspond à l'inclinaison de la manette qui donne le braquage complet.
- Sous Wayland, lance la version Linux native avec `SDL_VIDEODRIVER=x11` si Steam doit détecter le focus du jeu.

## Dépannage

- **« uinput indisponible »** : lance `sudo modprobe uinput`, puis ferme ta session et reconnecte-toi, ou relance `./install.sh`.
- **Manette non détectée** : débranche puis rebranche-la une fois après l'installation (règle udev).
- **Direction inversée** : active « Inverser la direction ».
- **Le jeu voit deux manettes** : laisse « Masquer la vraie DualSense » activé et utilise les options SDL ci-dessus.

La configuration est enregistrée dans `~/.config/ds5ctl/config.json`.

## Licence

MIT

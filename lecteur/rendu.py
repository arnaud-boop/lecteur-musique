"""Dessin des écrans du lecteur, en 240 x 240 pixels, avec Pillow.

Les boutons sont autour de l'écran : A en haut à gauche, B en bas à gauche,
X en haut à droite, Y en bas à droite. Une icône dans chaque coin rappelle
le rôle du bouton voisin. Ta fille lit peu : on montre surtout des images.
"""
import math
import unicodedata

from PIL import Image, ImageDraw, ImageFont

TAILLE = 240
NOIR = (0, 0, 0)
FOND = (18, 22, 38)
TEXTE = (246, 246, 250)
GRIS = (150, 158, 182)
ETEINT = (70, 78, 104)
PASTILLE = (36, 42, 68)
SELECTION = (52, 64, 112)
PISTE = (52, 60, 92)
ACCENT = (255, 199, 64)
ROSE = (255, 96, 128)
BLEU = (110, 170, 255)

COINS = {"A": (14, 30), "B": (14, 210), "X": (226, 30), "Y": (226, 210)}

POLICES = [
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",   # Mac
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",        # Pi (paquet fonts-dejavu-core)
]
_polices = {}
_masques = {}


def police(taille):
    if taille not in _polices:
        for chemin in POLICES:
            try:
                _polices[taille] = ImageFont.truetype(chemin, taille)
                break
            except OSError:
                continue
        else:
            _polices[taille] = ImageFont.load_default(size=taille)
    return _polices[taille]


# Écran complet

def dessiner(v, image_de, t):
    """Renvoie l'image de l'écran pour la vue `v` (un dictionnaire)."""
    sup = v.get("superposition")
    if v["ecran"] == "veille":
        img = Image.new("RGB", (TAILLE, TAILLE), NOIR)
        if sup and sup[0] == "soleil":
            _soleil(img, sup[1])
        return img
    if not v["allume"]:
        return Image.new("RGB", (TAILLE, TAILLE), NOIR)
    img = Image.new("RGB", (TAILLE, TAILLE), FOND)
    e = v["ecran"]
    if e == "config":
        _ecran_config(img)
    elif not v["soloist_ok"]:
        _ecran_attente(img, t)
    elif e == "chargement":
        _ecran_chargement(img, t)
    elif e == "playlists":
        _ecran_playlists(img, v, image_de, t)
    elif e == "titres":
        _ecran_titres(img, v, image_de, t)
    elif e == "lecture":
        _ecran_lecture(img, v, image_de, t)
    if sup:
        _superposition(img, sup, t)
    return img


def _ecran_playlists(img, v, image_de, t):
    d = ImageDraw.Draw(img)
    playlists = v["playlists"]
    if not playlists:
        texte(img, "Aucune playlist", police(18), 26, 108, 188, GRIS, t)
        coins(d, {"Y": ("retour", False)})
        return
    i = v["sel_playlist"]
    playlist = playlists[i]
    coller(img, image_de(playlist.get("image"), 150), 45, 12, 150)
    if v["playlist_en_cours"] == i:
        egaliseur(d, 176, 140, t, anime=v["en_lecture"])
    texte(img, playlist["nom"], police(21), 26, 170, 188, TEXTE, t)
    points(d, i, len(playlists), 120, 214)
    coins(d, {
        "A": ("haut", i > 0),
        "B": ("bas", i < len(playlists) - 1),
        "X": ("lecture", True),
        "Y": ("retour", v["peut_revenir"]),
    })


def _ecran_titres(img, v, image_de, t):
    d = ImageDraw.Draw(img)
    playlist = v["ouverte"]
    titres = playlist["titres"] if playlist else []
    n = len(titres)
    sel = v["sel_titre"]
    texte(img, playlist["nom"] if playlist else "", police(13), 30, 5, 180, GRIS, t, defiler=False)
    haut, ligne, visibles = 24, 53, 4
    premier = max(0, min(sel - 1, n - visibles))
    for k in range(visibles):
        j = premier + k
        if j >= n:
            break
        titre = titres[j]
        y = haut + k * ligne
        if j == sel:
            d.rounded_rectangle((26, y, 214, y + ligne - 4), 10, fill=SELECTION)
        coller(img, image_de(titre.get("vignette") or titre.get("image"), 44), 30, y + 4, 44, rayon=8)
        en_cours = v["ouverte_en_cours"] and titre["uri"] == v["titre_en_cours"]
        couleur = ACCENT if en_cours else (TEXTE if titre["jouable"] else ETEINT)
        texte(img, titre["nom"], police(16), 82, y + 7, 128, couleur, t, centrer=False, defiler=(j == sel))
        texte(img, titre["artistes"], police(12), 82, y + 29, 128, GRIS, t, centrer=False, defiler=False)
        if en_cours:
            egaliseur(d, 61, y + 44, t, petit=True, anime=v["en_lecture"])
        badge_avis(d, 69, y + 9, v["avis"].get(titre["uri"]))
    if not n:
        texte(img, "Playlist vide", police(16), 26, 110, 188, GRIS, t)
    coins(d, {
        "A": ("haut", sel > 0),
        "B": ("bas", sel < n - 1),
        "X": ("lecture", n > 0),
        "Y": ("retour", True),
    })


def _ecran_lecture(img, v, image_de, t):
    d = ImageDraw.Draw(img)
    lecture = v["lecture"]
    if not lecture:
        note(d, 120, 90, 60, ETEINT)
        coins(d, {"Y": ("retour", True)})
        return
    coller(img, image_de(lecture.get("image"), 150), 45, 8, 150)
    zone = (45, 8, 195, 158)
    if v["autre_appareil"]:
        voile(img, zone, 0.7)
        telephone(d, 120, 83, TEXTE)
    elif lecture["en_pause"]:
        voile(img, zone, 0.45)
        icone(d, "pause", 120, 83, TEXTE, r=22)
    badge_avis(d, 189, 14, lecture.get("avis"), r=14)
    texte(img, lecture["nom"], police(19), 26, 164, 188, TEXTE, t)
    texte(img, lecture["artistes"], police(13), 26, 189, 188, GRIS, t, defiler=False)
    x0, x1, y = 36, 204, 217
    d.rounded_rectangle((x0, y - 3, x1, y + 3), 3, fill=PISTE)
    if lecture["duree_ms"]:
        part = max(0.0, min(1.0, lecture["position_ms"] / lecture["duree_ms"]))
        d.rounded_rectangle((x0, y - 3, x0 + max(6, int((x1 - x0) * part)), y + 3), 3, fill=ACCENT)
    joue = not lecture["en_pause"] and not v["autre_appareil"]
    coins(d, {
        "A": ("precedent", True),
        "B": ("suivant", True),
        "X": ("pause" if joue else "lecture", True),
        "Y": ("retour", True),
    })


def _ecran_attente(img, t):
    d = ImageDraw.Draw(img)
    nuage(d, 120, 92, ETEINT)
    texte(img, "Soloist ne répond pas", police(14), 20, 150, 200, GRIS, t)


def _ecran_chargement(img, t):
    d = ImageDraw.Draw(img)
    debut = (t * 300) % 360
    d.arc((90, 70, 150, 130), debut, debut + 270, fill=ACCENT, width=7)
    texte(img, "Chargement", police(16), 20, 150, 200, GRIS, t)


def _ecran_config(img):
    d = ImageDraw.Draw(img)
    texte(img, "Mode configuration", police(18), 20, 92, 200, TEXTE)
    texte(img, "Bientôt disponible", police(13), 20, 122, 200, GRIS)
    coins(d, {"Y": ("retour", True)})


# Superpositions : cœur, visage triste, lune (veille), soleil (réveil)

def _superposition(img, sup, t):
    genre = sup[0]
    if genre in ("coeur", "triste"):
        voile(img, (0, 0, TAILLE, TAILLE), 0.55)
        d = ImageDraw.Draw(img)
        echelle = min(1.0, (t - sup[1]) / 0.25)
        if genre == "coeur":
            coeur(d, 120, 118, 120 * echelle, ROSE)
        else:
            visage_triste(d, 120, 120, 52 * echelle, BLEU, (18, 22, 38))
    elif genre == "lune":
        voile(img, (0, 0, TAILLE, TAILLE), 0.7)
        d = ImageDraw.Draw(img)
        anneau(d, 120, 120, 64, sup[1])
        lune(d, 120, 120, 38)


def _soleil(img, part):
    d = ImageDraw.Draw(img)
    anneau(d, 120, 120, 64, part)
    r = 24
    for k in range(8):
        a = k * math.pi / 4
        d.line((120 + math.cos(a) * (r + 8), 120 + math.sin(a) * (r + 8),
                120 + math.cos(a) * (r + 20), 120 + math.sin(a) * (r + 20)), fill=ACCENT, width=5)
    d.ellipse((120 - r, 120 - r, 120 + r, 120 + r), fill=ACCENT)


# Éléments

def coins(d, roles):
    """Dessine l'icône de chaque bouton dans son coin. roles = {bouton: (icône, actif)}."""
    for bouton, (genre, actif) in roles.items():
        cx, cy = COINS[bouton]
        d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill=PASTILLE)
        icone(d, genre, cx, cy, TEXTE if actif else ETEINT)


def icone(d, genre, cx, cy, couleur, r=7):
    if genre == "haut":
        d.polygon([(cx, cy - r), (cx + r, cy + r * 0.6), (cx - r, cy + r * 0.6)], fill=couleur)
    elif genre == "bas":
        d.polygon([(cx, cy + r), (cx + r, cy - r * 0.6), (cx - r, cy - r * 0.6)], fill=couleur)
    elif genre == "lecture":
        d.polygon([(cx - r * 0.6, cy - r), (cx + r, cy), (cx - r * 0.6, cy + r)], fill=couleur)
    elif genre == "pause":
        w = r * 0.55
        d.rectangle((cx - r * 0.8, cy - r, cx - r * 0.8 + w, cy + r), fill=couleur)
        d.rectangle((cx + r * 0.8 - w, cy - r, cx + r * 0.8, cy + r), fill=couleur)
    elif genre == "retour":
        d.polygon([(cx - r, cy), (cx - r * 0.1, cy - r * 0.85), (cx - r * 0.1, cy + r * 0.85)], fill=couleur)
        d.rectangle((cx - r * 0.2, cy - r * 0.3, cx + r, cy + r * 0.3), fill=couleur)
    elif genre == "precedent":
        d.rectangle((cx - r, cy - r * 0.8, cx - r * 0.65, cy + r * 0.8), fill=couleur)
        d.polygon([(cx - r * 0.55, cy), (cx + r, cy - r * 0.8), (cx + r, cy + r * 0.8)], fill=couleur)
    elif genre == "suivant":
        d.rectangle((cx + r * 0.65, cy - r * 0.8, cx + r, cy + r * 0.8), fill=couleur)
        d.polygon([(cx + r * 0.55, cy), (cx - r, cy - r * 0.8), (cx - r, cy + r * 0.8)], fill=couleur)


def texte(img, chaine, fonte, x, y, largeur, couleur, t=0.0, centrer=True, defiler=True):
    """Écrit une ligne. Trop longue : elle défile (ou finit par « … » si defiler=False)."""
    # Certains titres écrivent « é » en deux caractères (e + accent) : la police ne sait
    # pas les assembler et affiche un carré. On les regroupe en un seul caractère.
    chaine = unicodedata.normalize("NFC", chaine or "")
    d = ImageDraw.Draw(img)
    longueur = int(d.textlength(chaine, font=fonte))
    if longueur <= largeur:
        dx = (largeur - longueur) // 2 if centrer else 0
        d.text((x + dx, y), chaine, font=fonte, fill=couleur)
        return
    if not defiler:
        while chaine and d.textlength(chaine + "…", font=fonte) > largeur:
            chaine = chaine[:-1]
        d.text((x, y), chaine.rstrip() + "…", font=fonte, fill=couleur)
        return
    ecart, vitesse, pause = 40, 28.0, 1.5
    periode = (longueur + ecart) / vitesse + pause
    phase = t % periode
    decalage = 0 if phase < pause else int((phase - pause) * vitesse)
    montee, descente = fonte.getmetrics()
    calque = Image.new("RGBA", (largeur, montee + descente), (0, 0, 0, 0))
    dc = ImageDraw.Draw(calque)
    dc.text((-decalage, 0), chaine, font=fonte, fill=couleur)
    dc.text((-decalage + longueur + ecart, 0), chaine, font=fonte, fill=couleur)
    img.paste(calque, (x, y), calque)


def coller(img, source, x, y, taille, rayon=14):
    """Colle une pochette aux coins arrondis, ou une note si l'image n'est pas prête."""
    cle = (taille, rayon)
    if cle not in _masques:
        masque = Image.new("L", (taille, taille), 0)
        ImageDraw.Draw(masque).rounded_rectangle((0, 0, taille - 1, taille - 1), rayon, fill=255)
        _masques[cle] = masque
    if source is None:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x, y, x + taille - 1, y + taille - 1), rayon, fill=PISTE)
        note(d, x + taille / 2, y + taille / 2, taille * 0.45, GRIS)
        return
    if source.size != (taille, taille):
        source = source.resize((taille, taille))
    img.paste(source, (x, y), _masques[cle])


def voile(img, zone, force):
    """Assombrit une zone de l'écran (force entre 0 et 1)."""
    morceau = img.crop(zone)
    img.paste(Image.blend(morceau, Image.new("RGB", morceau.size, NOIR), force), zone[:2])


def points(d, i, n, cx, cy):
    if n <= 1:
        return
    if n > 9:
        chaine = f"{i + 1} / {n}"
        largeur = d.textlength(chaine, font=police(13))
        d.text((cx - largeur / 2, cy - 8), chaine, font=police(13), fill=GRIS)
        return
    pas = 13
    x0 = cx - pas * (n - 1) / 2
    for k in range(n):
        x = x0 + k * pas
        r = 4 if k == i else 3
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=ACCENT if k == i else ETEINT)


def egaliseur(d, x, y, t, petit=False, anime=True):
    """Trois barres : cette playlist ou ce titre est en cours.

    Elles bougent quand la musique joue, et restent immobiles et grises en pause.
    """
    largeur, hauteur = (3, 10) if petit else (5, 18)
    fixes = (0.55, 0.9, 0.4)
    for k in range(3):
        part = 0.35 + 0.65 * abs(math.sin(t * 4 + k * 1.7)) if anime else fixes[k]
        h = hauteur * part
        x0 = x + k * (largeur + 2)
        d.rectangle((x0, y - h, x0 + largeur, y), fill=ACCENT if anime else GRIS)


def badge_avis(d, cx, cy, avis, r=9):
    """Petit rond avec un cœur (j'aime) ou un visage triste (je n'aime pas)."""
    if avis not in ("aime", "naime_pas"):
        return
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=PASTILLE)
    if avis == "aime":
        coeur(d, cx, cy - r * 0.05, r * 1.15, ROSE)
    else:
        visage_triste(d, cx, cy, r * 0.8, BLEU, PASTILLE)


def note(d, cx, cy, s, couleur):
    d.ellipse((cx - s * 0.5, cy + s * 0.1, cx + s * 0.05, cy + s * 0.55), fill=couleur)
    d.rectangle((cx - s * 0.03, cy - s * 0.6, cx + s * 0.06, cy + s * 0.35), fill=couleur)
    d.polygon([(cx + s * 0.06, cy - s * 0.6), (cx + s * 0.45, cy - s * 0.35),
               (cx + s * 0.45, cy - s * 0.15), (cx + s * 0.06, cy - s * 0.4)], fill=couleur)


def coeur(d, cx, cy, taille, couleur):
    if taille < 4:
        return
    r = taille * 0.25
    d.ellipse((cx - 2 * r, cy - 1.5 * r, cx, cy + 0.5 * r), fill=couleur)
    d.ellipse((cx, cy - 1.5 * r, cx + 2 * r, cy + 0.5 * r), fill=couleur)
    d.polygon([(cx - 1.93 * r, cy - 0.1 * r), (cx + 1.93 * r, cy - 0.1 * r), (cx, cy + 1.9 * r)], fill=couleur)


def visage_triste(d, cx, cy, r, couleur, fond):
    if r < 4:
        return
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=couleur)
    o = r * 0.14
    for sx in (-1, 1):
        d.ellipse((cx + sx * r * 0.38 - o, cy - r * 0.3 - o, cx + sx * r * 0.38 + o, cy - r * 0.3 + o), fill=fond)
    d.arc((cx - r * 0.5, cy + r * 0.2, cx + r * 0.5, cy + r * 0.9), 200, 340, fill=fond,
          width=max(3, int(r * 0.12)))


def lune(d, cx, cy, r):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
    d.ellipse((cx - r * 0.45, cy - r * 1.05, cx + r * 1.4, cy + r * 0.8), fill=(8, 10, 18))


def anneau(d, cx, cy, r, part):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=PISTE, width=7)
    if part > 0:
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * min(1.0, part), fill=ACCENT, width=7)


def telephone(d, cx, cy, couleur):
    d.rounded_rectangle((cx - 14, cy - 24, cx + 14, cy + 24), 6, outline=couleur, width=4)
    d.ellipse((cx - 3, cy + 13, cx + 3, cy + 19), fill=couleur)


def nuage(d, cx, cy, couleur):
    d.ellipse((cx - 44, cy - 6, cx - 6, cy + 30), fill=couleur)
    d.ellipse((cx - 22, cy - 30, cx + 22, cy + 14), fill=couleur)
    d.ellipse((cx + 4, cy - 12, cx + 44, cy + 28), fill=couleur)
    d.rectangle((cx - 26, cy + 10, cx + 26, cy + 30), fill=couleur)

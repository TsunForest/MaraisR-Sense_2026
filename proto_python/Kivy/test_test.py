# -*- coding: utf-8 -*-
# Jeu de solitaire (plateau 7x7) pour UNIHIKER
# BTS CIEL - Projet Python sur écran tactile UNIHIKER

from unihiker import GUI
import time

# Constantes du plateau
ROWS = 7
COLS = 7
INVALID = -1  # case inutilisable (en dehors de la croix)
EMPTY = 0     # case vide
PEG = 1       # case avec un pion

# Taille et position des "cases" à l'écran (en pixels)
CELL_SIZE = 30
CELL_GAP = 5
OFFSET_X = 5          # marge gauche
OFFSET_Y = 40         # marge haute pour laisser de la place au texte

# Objets globaux
gui = GUI()
board = []            # logique du plateau
buttons = []          # boutons graphiques correspondants
selected = None       # (row, col) du pion actuellement sélectionné, ou None
status_text = None    # texte d’état en haut de l’écran


def init_board():
    """Initialise la grille logique du solitaire (croix 7x7, centre vide)."""
    global board
    # Plateau plein de pions au départ
    board = [[PEG for _ in range(COLS)] for _ in range(ROWS)]

    # On met les coins à INVALID pour obtenir la forme en croix
    for r in range(ROWS):
        for c in range(COLS):
            if (r < 2 or r > 4) and (c < 2 or c > 4):
                board[r][c] = INVALID

    # Case centrale vide
    board[3][3] = EMPTY


def create_gui():
    """Crée les boutons pour chaque case et le texte d’information."""
    global buttons, status_text
    buttons = []

    # Texte d’état en haut de l’écran
    status_text = gui.draw_text(
        text="Solitaire - Sélectionnez un pion",
        x=120, y=15,
        font_size=12,
        origin="center",
        color="#000000"
    )

    for r in range(ROWS):
        row_btns = []
        for c in range(COLS):
            if board[r][c] == INVALID:
                # Pas de bouton pour les cases invalides
                row_btns.append(None)
                continue

            # Calcul de la position (centre du bouton)
            x = OFFSET_X + c * (CELL_SIZE + CELL_GAP) + CELL_SIZE // 2
            y = OFFSET_Y + r * (CELL_SIZE + CELL_GAP) + CELL_SIZE // 2

            # Texte du bouton selon l’état de la case
            txt = "●" if board[r][c] == PEG else "·"

            # Création du bouton avec callback vers on_cell_click
            btn = gui.add_button(
                x=x,
                y=y,
                w=CELL_SIZE,
                h=CELL_SIZE,
                text=txt,
                origin="center",
                onclick=lambda rr=r, cc=c: on_cell_click(rr, cc)
            )
            row_btns.append(btn)
        buttons.append(row_btns)

    # Bouton pour réinitialiser la partie
    gui.add_button(
        x=120,
        y=300,
        w=100,
        h=30,
        text="Réinitialiser",
        origin="center",
        onclick=reset_game
    )


def update_display():
    """Met à jour l’affichage des boutons en fonction du plateau."""
    for r in range(ROWS):
        for c in range(COLS):
            btn = buttons[r][c] if r < len(buttons) and buttons[r][c] else None
            if board[r][c] == INVALID or btn is None:
                continue

            # Texte pour pion ou case vide
            txt = "●" if board[r][c] == PEG else "·"

            # Couleur de fond normale
            bg = "#FFFFFF"

            # Si cette case est sélectionnée, on la surligne
            if selected is not None and (r, c) == selected:
                bg = "#FFFF99"

            # Mise à jour du bouton
            btn.config(text=txt, bg=bg)

    # Mise à jour du texte d’état si la partie est finie ou bloquée
    remaining = count_pegs()
    if remaining == 1 and board[3][3] == PEG:
        status_text.config(text="Bravo ! Il ne reste qu’un pion au centre.")
    elif remaining == 1:
        status_text.config(text="Il ne reste qu’un pion, presque parfait !")
    elif not has_moves():
        status_text.config(text="Plus de coups possibles… Appuyez sur Réinitialiser.")
    else:
        # On garde un texte neutre si la partie continue
        status_text.config(text="Solitaire - Pions restants : {}".format(remaining))


def on_cell_click(r, c):
    """Gestion d’un clic sur une case (sélection + déplacement)."""
    global selected

    # Ignorer les cases invalides
    if board[r][c] == INVALID:
        return

    # Si aucun pion n’est encore sélectionné
    if selected is None:
        if board[r][c] == PEG:
            # Sélectionner ce pion
            selected = (r, c)
        # Si on clique sur une case vide sans sélection, on ne fait rien
    else:
        sr, sc = selected

        # Si on reclique sur la même case : désélection
        if (r, c) == (sr, sc):
            selected = None
        else:
            # Tenter un déplacement du pion sélectionné vers (r, c)
            if try_move(sr, sc, r, c):
                # Déplacement réussi, on annule la sélection
                selected = None
            else:
                # Si le clic est sur un autre pion, on change de sélection
                if board[r][c] == PEG:
                    selected = (r, c)
                # Sinon, on garde la sélection actuelle

    update_display()


def try_move(sr, sc, tr, tc):
    """Tente de déplacer un pion de (sr, sc) vers (tr, tc). Renvoie True si ok."""
    # Vérifier que la case source contient un pion
    if board[sr][sc] != PEG:
        return False

    # La case cible doit être vide
    if board[tr][tc] != EMPTY:
        return False

    dr = tr - sr
    dc = tc - sc

    # Mouvement uniquement horizontal ou vertical, de 2 cases
    if abs(dr) == 2 and dc == 0:
        mr = sr + dr // 2
        mc = sc
    elif abs(dc) == 2 and dr == 0:
        mr = sr
        mc = sc + dc // 2
    else:
        return False

    # La case « sautée » doit contenir un pion
    if board[mr][mc] != PEG:
        return False

    # Appliquer le coup
    board[sr][sc] = EMPTY
    board[mr][mc] = EMPTY
    board[tr][tc] = PEG
    return True


def count_pegs():
    """Compte le nombre de pions restants sur le plateau."""
    count = 0
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] == PEG:
                count += 1
    return count


def has_moves():
    """Teste s’il reste au moins un coup possible."""
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] != PEG:
                continue

            # Essayer les 4 directions possibles (2 cases plus loin)
            directions = [(-2, 0), (2, 0), (0, -2), (0, 2)]
            for dr, dc in directions:
                tr = r + dr
                tc = c + dc
                # Vérifier les bornes
                if 0 <= tr < ROWS and 0 <= tc < COLS:
                    if board[tr][tc] == EMPTY:
                        # Vérifier qu’il y a un pion entre les deux
                        mr = r + dr // 2
                        mc = c + dc // 2
                        if board[mr][mc] == PEG:
                            return True
    return False


def reset_game():
    """Callback du bouton Réinitialiser : relance une partie neuve."""
    global selected
    selected = None
    init_board()
    update_display()


# ---------------- Programme principal ----------------

init_board()
create_gui()
update_display()

# Boucle infinie pour laisser vivre l’interface graphique
while True:
    time.sleep(0.1)

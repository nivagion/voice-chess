import os
import chess
import threading


# veličina polja u pikselima
TILE = 80
# širina okvira oko ploče u pikselima
BORDER = 20
# boje polja
LIGHT = (240, 217, 181)
DARK  = (181, 136, 99)
# boja zadnjeg poteza
HL_LAST = (246, 246, 105)

# padding oko ploče za ispis oznaka (file/rank) i info linije
PAD_LEFT   = 28  # brojevi rankova
PAD_RIGHT  = 28  # brojevi rankova
PAD_TOP    = 22  # bvoje fileova
PAD_BOTTOM = 52  # brojevi fileova + info linija

# Putanja do foldera sa slikama figura
FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")

# Ove varijable viewer koristi kao flagove / cache
_enabled = False  # True ako je init() uspio i prozor je aktivan
_warned = False
_piece_cache = {}
_screen = None
_info_font = None

# Mapiranje tipa figure na slovo iz imena PNG datoteka
PIECE_LETTER = {
    chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b',
    chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k',
}

def configure(*, figures_dir: str | None = None, tile: int | None = None):
    """Zvati prije init() ako se želi promijeniti default lokaciju za slike ili veličinu polja."""
    global FIGURES_DIR, TILE
    if figures_dir:
        FIGURES_DIR = figures_dir
    if tile:
        TILE = int(tile)

def init(width: int | None = None, height: int | None = None, caption="Voice Chess — Board View") -> bool:
                # width/height su ili int ili None, a funkcija vraća bool koji kaže je li viewer aktivan
    """
    Inicijalizira viewer. Vraća True ako je prozor uspješno pokrenut, False ako je viewer onemogućen
    (npr. nema pygame-a ili asseta).
    Funkciju je sigurno zvati više puta; ako je već inicijalizirano, napravi se no-op.
    """
    global _enabled, _screen, _info_font, _warned
    if _enabled:  # već je sve spremno
        return True
    try:
        import pygame
    except Exception:
        if not _warned:
            print("[viewer] pygame not available; viewer disabled.")
            _warned = True
        return False

    pygame.init()
    # izračunaj window size (ploča + border + padovi za oznake)
    board_size = TILE * 8
    w = board_size + BORDER*2 + PAD_LEFT + PAD_RIGHT
    h = board_size + BORDER*2 + PAD_TOP + PAD_BOTTOM
    if width and height:
        w, h = width, height
    _screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption(caption)
    _info_font = pygame.font.SysFont(None, 24)
    _enabled = True
    return True

def pump():
    """Obrađuje pygame evente da prozor ostane responzivan; omogućuje zatvaranje prozora bez rušenja igre."""
    global _enabled, _screen
    if not _enabled or _screen is None:
        return
    import pygame
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            pygame.display.quit()
            pygame.quit()
            _screen = None
            _enabled = False
            return

def render(board: chess.Board):
    """Iscrtava trenutno stanje šahovske ploče. Ako viewer nije aktivan, funkcija ne radi ništa."""
    if not _enabled or _screen is None:
        return
    import pygame

    def square_to_rc(square: int):
        # Pretvara indeks polja (0-63) u redak i stupac
        rank = 7 - chess.square_rank(square)
        file = chess.square_file(square)
        return rank, file

    def get_piece_image(piece: chess.Piece):
        # uzima Surface za figuru iz cachea ili je učitava s diska i sprema u cache
        key = (piece.piece_type, piece.color, TILE)
        if key in _piece_cache:
            return _piece_cache[key]
        letter = PIECE_LETTER[piece.piece_type]   # 'p','r','n','b','q','k'
        color_ch = 'l' if piece.color == chess.WHITE else 'd'
        filename = f"Chess_{letter}{color_ch}t60.png"
        path = os.path.join(FIGURES_DIR, filename)
        if not os.path.isfile(path):
            nonlocal_warn_missing(path)
            # fallback ako nema figure
            img = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            pygame.draw.circle(
                img,
                (0, 0, 0) if piece.color == chess.BLACK else (255, 255, 255),
                (TILE // 2, TILE // 2),
                TILE // 3,
                0,
            )
        else:
            img = pygame.image.load(path).convert_alpha()
            if img.get_width() != TILE or img.get_height() != TILE:
                img = pygame.transform.smoothscale(img, (TILE, TILE))
        _piece_cache[key] = img
        return img

    def nonlocal_warn_missing(path):
        # print upozorenje za nedostajuću sliku samo jednom po nazivu datoteke
        key = ("missing", os.path.basename(path))
        if key not in _piece_cache:
            print(f"[viewer] Missing piece image: {path}")
            _piece_cache[key] = True

    board_size = TILE * 8

    # Početne koordinate (gornji lijevi kut polja a8)
    origin_x = BORDER + PAD_LEFT
    origin_y = BORDER + PAD_TOP

    # Pozadina oko ploče
    _screen.fill((230, 230, 230))

    # Iscrtavanje polja (svijetlo/tamno)
    for row in range(8):
        for col in range(8):
            color = LIGHT if (row + col) % 2 == 0 else DARK
            rect = pygame.Rect(origin_x + col*TILE, origin_y + row*TILE, TILE, TILE)
            pygame.draw.rect(_screen, color, rect)

    # Isticanje zadnjeg poteza (iz polja i u polje)
    if board.move_stack:
        last = board.peek()
        for sq in (last.from_square, last.to_square):
            r, c = square_to_rc(sq)
            rect = pygame.Rect(origin_x + c*TILE, origin_y + r*TILE, TILE, TILE)
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            s.fill((*HL_LAST, 60))
            _screen.blit(s, rect.topleft)

    # Crtanje figura
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece:
            continue
        r, c = square_to_rc(sq)
        img = get_piece_image(piece)
        _screen.blit(img, (origin_x + c*TILE, origin_y + r*TILE))

    # Oznake fileova (a-h) dolje i gore
    files = "abcdefgh"
    for col in range(8):
        ch = files[col]
        t = _info_font.render(ch, True, (10, 10, 10))
        # dolje
        rect_b = t.get_rect(midtop=(origin_x + col*TILE + TILE/2, origin_y + board_size + 6))
        _screen.blit(t, rect_b)
        # gore
        rect_t = t.get_rect(midbottom=(origin_x + col*TILE + TILE/2, origin_y - 6))
        _screen.blit(t, rect_t)

    # Oznake rankova (8-1) lijevo i desno
    for row in range(8):
        ch = str(8 - row)
        t = _info_font.render(ch, True, (10, 10, 10))
        cy = origin_y + row*TILE + TILE/2
        # lijevo
        rect_l = t.get_rect(midright=(origin_x - 6, cy))
        _screen.blit(t, rect_l)
        # desno
        rect_r = t.get_rect(midleft=(origin_x + board_size + 6, cy))
        _screen.blit(t, rect_r)

    # info linija na dnu (čiji je potez + hint da se prozor može zatvoriti)
    msg = f"Turn: {'White' if board.turn == chess.WHITE else 'Black'}"
    info = _info_font.render(msg + "  |  Close window to hide viewer", True, (10, 10, 10))
    _screen.blit(info, (origin_x, origin_y + board_size + 24))

    pygame.display.flip()

def close():
    """Zatvara viewer prozor (opcionalno; sigurno zvati više puta)."""
    global _enabled, _screen
    if not _enabled or _screen is None:
        return
    import pygame
    pygame.display.quit()
    pygame.quit()
    _screen = None
    _enabled = False

import os
import chess
import threading


# veličina polja u pikselima
TILE = 80
BORDER = 20
# boje polja
LIGHT = (240, 217, 181)
DARK  = (181, 136, 99)
HL_LAST = (246, 246, 105)

# padding oko ploče
PAD_LEFT   = 28 # space for rank numbers on the left
PAD_RIGHT  = 28 # space for rank numbers on the right
PAD_TOP    = 22 # space for file letters on the top
PAD_BOTTOM = 52 # space for file letters + info line at the bottom

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")

# ovo koristi viewer kao flagove
_enabled = False # True ako init() uspije
_warned = False
_piece_cache = {}
_screen = None
_info_font = None

PIECE_LETTER = {
    chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b',
    chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k',
}

def configure(*, figures_dir: str | None = None, tile: int | None = None):
    """zvati prije init() ako se želi promijeniti default lokacija za slike ili veličina polja"""
    global FIGURES_DIR, TILE
    if figures_dir:
        FIGURES_DIR = figures_dir
    if tile:
        TILE = int(tile)

def init(width: int | None = None, height: int | None = None, caption="Voice Chess — Board View") -> bool:
                # ili je int ili None, a return type je bool
    """
    Initialize the viewer. Returns True if window is active, False if disabled (no pygame/assets).
    Safe to call multiple times; a no-op if already enabled.
    """
    global _enabled, _screen, _info_font, _warned
    if _enabled:  # already good
        return True
    try:
        import pygame
    except Exception:
        if not _warned:
            print("[viewer] pygame not available; viewer disabled.")
            _warned = True
        return False

    pygame.init()
    # compute window size (board + border + label pads)
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
    """Keep the window responsive; allows closing the window without killing the game."""
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
    """Draw the current board state. No-op if viewer not enabled."""
    if not _enabled or _screen is None:
        return
    import pygame

    def square_to_rc(square: int):
        # row 0 is top; col 0 is left
        rank = 7 - chess.square_rank(square)
        file = chess.square_file(square)
        return rank, file

    def get_piece_image(piece: chess.Piece):
        key = (piece.piece_type, piece.color, TILE)
        if key in _piece_cache:
            return _piece_cache[key]
        letter = PIECE_LETTER[piece.piece_type]   # 'p','r','n','b','q','k'
        color_ch = 'l' if piece.color == chess.WHITE else 'd'
        filename = f"Chess_{letter}{color_ch}t60.png"
        path = os.path.join(FIGURES_DIR, filename)
        if not os.path.isfile(path):
            nonlocal_warn_missing(path)
            # fallback circle placeholder
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
        # Print once per missing filename
        key = ("missing", os.path.basename(path))
        if key not in _piece_cache:
            print(f"[viewer] Missing piece image: {path}")
            _piece_cache[key] = True

    board_size = TILE * 8

    # origins (top-left of a8 square)
    origin_x = BORDER + PAD_LEFT
    origin_y = BORDER + PAD_TOP

    # background
    _screen.fill((230, 230, 230))

    # squares
    for row in range(8):
        for col in range(8):
            color = LIGHT if (row + col) % 2 == 0 else DARK
            rect = pygame.Rect(origin_x + col*TILE, origin_y + row*TILE, TILE, TILE)
            pygame.draw.rect(_screen, color, rect)

    # last move highlight
    if board.move_stack:
        last = board.peek()
        for sq in (last.from_square, last.to_square):
            r, c = square_to_rc(sq)
            rect = pygame.Rect(origin_x + c*TILE, origin_y + r*TILE, TILE, TILE)
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            s.fill((*HL_LAST, 60))
            _screen.blit(s, rect.topleft)

    # pieces
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece:
            continue
        r, c = square_to_rc(sq)
        img = get_piece_image(piece)
        _screen.blit(img, (origin_x + c*TILE, origin_y + r*TILE))

    # file letters (a-h) bottom and top
    files = "abcdefgh"
    for col in range(8):
        ch = files[col]
        t = _info_font.render(ch, True, (10, 10, 10))
        # bottom
        rect_b = t.get_rect(midtop=(origin_x + col*TILE + TILE/2, origin_y + board_size + 6))
        _screen.blit(t, rect_b)
        # top
        rect_t = t.get_rect(midbottom=(origin_x + col*TILE + TILE/2, origin_y - 6))
        _screen.blit(t, rect_t)

    # rank numbers (8-1) left and right
    for row in range(8):
        ch = str(8 - row)
        t = _info_font.render(ch, True, (10, 10, 10))
        cy = origin_y + row*TILE + TILE/2
        # left
        rect_l = t.get_rect(midright=(origin_x - 6, cy))
        _screen.blit(t, rect_l)
        # right
        rect_r = t.get_rect(midleft=(origin_x + board_size + 6, cy))
        _screen.blit(t, rect_r)

    # info line
    msg = f"Turn: {'White' if board.turn == chess.WHITE else 'Black'}"
    info = _info_font.render(msg + "  |  Close window to hide viewer", True, (10, 10, 10))
    _screen.blit(info, (origin_x, origin_y + board_size + 24))

    pygame.display.flip()

def close():
    """Close the viewer window (optional)."""
    global _enabled, _screen
    if not _enabled or _screen is None:
        return
    import pygame
    pygame.display.quit()
    pygame.quit()
    _screen = None
    _enabled = False

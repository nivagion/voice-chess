# viewer.py
import os
import chess
import threading


# ---------- Public config ----------
TILE = 80
BORDER = 20
LIGHT = (240, 217, 181)
DARK  = (181, 136, 99)
HL_LAST = (246, 246, 105)

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")

# ---------- Internal state ----------
_enabled = False         # True after init() if pygame + assets okay
_warned = False          # print warning only once
_piece_cache = {}
_screen = None
_info_font = None


PIECE_LETTER = {
    chess.PAWN: 'p', chess.KNIGHT: 'n', chess.BISHOP: 'b',
    chess.ROOK: 'r', chess.QUEEN: 'q', chess.KING: 'k',
}

def configure(*, figures_dir: str | None = None, tile: int | None = None):
    """Call before init() if you want to override defaults."""
    global FIGURES_DIR, TILE
    if figures_dir:
        FIGURES_DIR = figures_dir
    if tile:
        TILE = int(tile)

def init(width: int | None = None, height: int | None = None, caption="Voice Chess — Board View") -> bool:
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
    # compute window size
    board_size = TILE * 8
    w = h = board_size + BORDER * 2
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
    width = height = board_size + BORDER * 2

    # background
    _screen.fill((230, 230, 230))

    # squares
    for row in range(8):
        for col in range(8):
            color = LIGHT if (row + col) % 2 == 0 else DARK
            rect = pygame.Rect(BORDER + col*TILE, BORDER + row*TILE, TILE, TILE)
            pygame.draw.rect(_screen, color, rect)

    # last move highlight
    if board.move_stack:
        last = board.peek()
        for sq in (last.from_square, last.to_square):
            r, c = square_to_rc(sq)
            rect = pygame.Rect(BORDER + c*TILE, BORDER + r*TILE, TILE, TILE)
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
        _screen.blit(img, (BORDER + c*TILE, BORDER + r*TILE))

    # info line
    msg = f"Turn: {'White' if board.turn == chess.WHITE else 'Black'}"
    text = _info_font.render(msg + "  |  Close window to hide viewer", True, (10,10,10))
    _screen.blit(text, (BORDER, height - BORDER + 2))

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

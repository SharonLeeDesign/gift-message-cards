#!/usr/bin/env python3
"""
Sharon Lee Design - Gift Message card generator.

Takes a JSON list of {"order": "#1022", "message": "..."} and produces a
print-ready PDF: A4 landscape sheets, 4 square cards per sheet (2x2 grid),
matching the look of Sharon's "Gift Message.ai" template (dark green ink,
vine motif down the right-hand side, EB Garamond). Any unused card slot on
the last sheet is left as a blank template card.

Usage:
    python3 generate_gift_cards.py --input cards.json --output out.pdf

cards.json format:
    [
      {"order": "#1022", "message": "Happy birthday! Love, Mum x"},
      {"order": "#1030", "message": "Congratulations on the new home!"}
    ]

Anything that needs a human to look (font or artwork missing, a message too
long to fit) is printed as a line starting "WARNING:" so the caller can pass
it on. A missing font or vine never stops the PDF being made.
"""
import argparse
import json
import os
import sys

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
VINE_IMAGE = os.path.join(HERE, "assets", "vine.png")
FONT_REGULAR = os.path.join(HERE, "fonts", "EBGaramond-Regular.ttf")
FONT_ITALIC = os.path.join(HERE, "fonts", "EBGaramond-Italic.ttf")

INK = (25 / 255, 57 / 255, 44 / 255)  # dark green, sampled from the original design
MUTED = (0.55, 0.55, 0.52)

HEADING_FONT_NAME = "EBGaramond"
BODY_FONT_NAME = "EBGaramond"
BODY_ITALIC_FONT_NAME = "EBGaramond-Italic"

PAGE_W, PAGE_H = landscape(A4)  # 841.89 x 595.28 pt

CARD_SIZE = 255  # pt, square card (~90mm)
GRID_COLS, GRID_ROWS = 2, 2
GUTTER = 12
OUTER_MARGIN_X = (PAGE_W - (CARD_SIZE * GRID_COLS + GUTTER * (GRID_COLS - 1))) / 2
OUTER_MARGIN_Y = (PAGE_H - (CARD_SIZE * GRID_ROWS + GUTTER * (GRID_ROWS - 1))) / 2
CUT_INSET = 10
PADDING = 20
LEAF_WIDTH_FRAC = 0.34  # the vine never takes more than this share of the card width

warnings = []


def warn(msg):
    warnings.append(msg)
    print(f"WARNING: {msg}")


def register_fonts():
    """Register EB Garamond from the repo's fonts/ folder. Falls back to the
    built-in Times fonts (with a warning) rather than failing the batch."""
    global HEADING_FONT_NAME, BODY_FONT_NAME, BODY_ITALIC_FONT_NAME
    try:
        pdfmetrics.registerFont(TTFont(HEADING_FONT_NAME, FONT_REGULAR))
    except Exception:
        warn("EB Garamond (fonts/EBGaramond-Regular.ttf) could not be loaded; cards use Times instead.")
        HEADING_FONT_NAME = BODY_FONT_NAME = "Times-Roman"
        BODY_ITALIC_FONT_NAME = "Times-Italic"
        return
    try:
        pdfmetrics.registerFont(TTFont(BODY_ITALIC_FONT_NAME, FONT_ITALIC))
    except Exception:
        BODY_ITALIC_FONT_NAME = HEADING_FONT_NAME  # only used for the small order label


def load_vine():
    try:
        vine = ImageReader(VINE_IMAGE)
        vine.getSize()
        return vine
    except Exception:
        warn("Vine artwork (assets/vine.png) could not be loaded; cards print without it.")
        return None


def split_long_word(c, word, font_name, font_size, max_width):
    """Break a single word wider than the column (e.g. a URL) into pieces."""
    pieces, cur = [], ""
    for ch in word:
        if cur and c.stringWidth(cur + ch, font_name, font_size) > max_width:
            pieces.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        pieces.append(cur)
    return pieces


def wrap_text(c, text, font_name, font_size, max_width):
    """Word-wrap text to max_width, PRESERVING explicit line breaks the
    customer actually typed - only overlong lines within a paragraph wrap."""
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for para in paragraphs:
        if para.strip() == "":
            lines.append("")
            continue
        words = []
        for w in para.split():
            if c.stringWidth(w, font_name, font_size) > max_width:
                words.extend(split_long_word(c, w, font_name, font_size, max_width))
            else:
                words.append(w)
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if c.stringWidth(trial, font_name, font_size) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def fit_message(c, message, font_name, max_width, max_height, max_size=13, min_size=7.5):
    """Largest font size (13pt down to 7.5pt) at which the message fits.
    Returns (size, lines, leading, fits)."""
    size = max_size
    while size >= min_size:
        leading = size * 1.28
        lines = wrap_text(c, message, font_name, size, max_width)
        if len(lines) * leading <= max_height:
            return size, lines, leading, True
        size -= 0.5
    lines = wrap_text(c, message, font_name, min_size, max_width)
    return min_size, lines, min_size * 1.28, False


def draw_card(c, x, y, order_name, message, column, vine):
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.5)
    c.rect(x, y, CARD_SIZE, CARD_SIZE)

    inset = CUT_INSET
    ix, iy, isize = x + inset, y + inset, CARD_SIZE - inset * 2
    c.setLineWidth(1)
    c.rect(ix, iy, isize, isize)

    # Vine down the right-hand side, full height, never wider than LEAF_WIDTH_FRAC.
    max_leaf_w = isize * LEAF_WIDTH_FRAC
    leaf_w = max_leaf_w
    if vine is not None:
        lw_px, lh_px = vine.getSize()
        leaf_h = isize - PADDING * 1.6
        leaf_w = min(leaf_h * (lw_px / lh_px), max_leaf_w)
        leaf_h = leaf_w * (lh_px / lw_px)
        leaf_x = ix + isize - PADDING * 0.9 - leaf_w
        leaf_y = iy + (isize - leaf_h) / 2
        c.drawImage(vine, leaf_x, leaf_y, width=leaf_w, height=leaf_h,
                    mask="auto", preserveAspectRatio=True)

    text_right_edge = ix + isize - PADDING * 0.9 - leaf_w - 10
    text_width = text_right_edge - (ix + PADDING)

    c.setFillColorRGB(*INK)
    c.setFont(HEADING_FONT_NAME, 15)
    heading_y = iy + isize - PADDING - 12
    c.drawString(ix + PADDING, heading_y, "Gift Message")

    if message:
        body_top = heading_y - 22
        max_h = body_top - (iy + PADDING)
        size, lines, leading, fits = fit_message(c, message, BODY_FONT_NAME, text_width, max_h)
        if not fits:
            warn(f"{order_name}: message is too long for the card even at the smallest "
                 f"text size - check the printed card before sending.")
        c.setFont(BODY_FONT_NAME, size)
        ty = body_top
        for line in lines:
            c.drawString(ix + PADDING, ty, line)
            ty -= leading

    if order_name:
        # Order number sits in the margin outside the card, so it's trimmed off.
        c.setFillColorRGB(*MUTED)
        c.setFont(BODY_ITALIC_FONT_NAME, 8)
        label_y = y + 12
        gap = 8
        if column == "left":
            c.drawRightString(x - gap, label_y, order_name)
        else:
            c.drawString(x + CARD_SIZE + gap, label_y, order_name)


def generate(cards, output_path):
    register_fonts()
    vine = load_vine()
    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))

    items = list(cards)
    while len(items) % 4 != 0:
        items.append(None)
    if not items:
        items = [None] * 4

    positions = [
        (OUTER_MARGIN_X, OUTER_MARGIN_Y + CARD_SIZE + GUTTER, "left"),
        (OUTER_MARGIN_X + CARD_SIZE + GUTTER, OUTER_MARGIN_Y + CARD_SIZE + GUTTER, "right"),
        (OUTER_MARGIN_X, OUTER_MARGIN_Y, "left"),
        (OUTER_MARGIN_X + CARD_SIZE + GUTTER, OUTER_MARGIN_Y, "right"),
    ]
    for page_start in range(0, len(items), 4):
        for item, (x, y, column) in zip(items[page_start:page_start + 4], positions):
            if item is None:
                draw_card(c, x, y, None, None, column, vine)
            else:
                draw_card(c, x, y, item.get("order", ""), item.get("message", ""), column, vine)
        c.showPage()

    c.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    with open(args.input) as f:
        cards = json.load(f)
    generate(cards, args.output)
    print(f"Wrote {args.output} ({len(cards)} card(s), {len(warnings)} warning(s))")


if __name__ == "__main__":
    sys.exit(main())

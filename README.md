# Gift message cards (Sharon Lee Design)

This repo turns customers' gift messages from sharonlee.co.uk orders into print-ready cards: A4 landscape, four square cards per sheet.

## How it fits together

1. **Shopify Flow: "Gift message to order note + tag (Click & Drop)".**
   - Runs the moment an order with a non-empty "Gift Message" is placed.
   - Copies the message into the order note, which is what Royal Mail Click & Drop shows.
   - Tags the order `gift-message`.
   - Emails Michael.
2. **The Claude scheduled task** (Cowork routine):
   - When it runs:
     - daily at 6am UK time;
     - hourly from 7am to 7pm, 15 Nov to 15 Jan.
   - What it does: downloads this repo, follows [RUNBOOK.md](RUNBOOK.md), makes the PDF, and pushes it to the Claude app.
   - Afterwards it tags each order `giftcard-printed`, so the order is never printed twice.
   - If there's nothing to print, it stays silent.
3. **One-off reprint:** in any Claude chat, ask "run the gift card routine for #1150".

## Files

| File | What |
|---|---|
| `generate_gift_cards.py` | Makes the PDF from a JSON list of `{"order", "message"}` |
| `RUNBOOK.md` | Step-by-step instructions the scheduled task follows |
| `assets/vine.png` | The vine artwork. **Temporary:** cut from the 2021 JPG. Replace it with Sharon's clean export from `Packaging/Gift Message.ai` (same file name) |
| `fonts/` | EB Garamond Regular and Italic (TrueType), SIL Open Font Licence (`fonts/OFL.txt`) |

## Try it locally

```bash
pip install reportlab
python3 generate_gift_cards.py --input sample.json --output test.pdf
```

Any line in the output starting `WARNING:` (missing font or artwork, or a message too long to fit) needs a human to check. The PDF is still made.

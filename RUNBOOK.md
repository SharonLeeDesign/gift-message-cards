# Gift message cards: runbook for the scheduled run

This file is read by the Claude scheduled task (Cowork routine) each time it runs. The task's own prompt is just a few lines: download this repo, then follow this file. To change how the run behaves, edit this file (no need to touch the scheduled task).

Unattended run: nobody is watching. Don't ask questions, just do the work and finish.

## 0. Which kind of run is this?

- **Ad-hoc / reprint.** The message that started this run names a specific order, for example "reprint the gift card for #1150" or "card for #1150". Look up **that order only**, by name, with a GraphQL query of `name:#1150`. Build its card(s) with the rules in step 2, then do steps 3–5, even if it already has the `giftcard-printed` tag. Send the PDF with status `normal`. If the order has no non-empty gift message, say so plainly. Don't make a blank card.
- **"Run today's batch now"** (asked in a chat). Do the normal batch below, but send with status `normal`.
- **Hourly Christmas run.** The prompt says "HOURLY". First check the UK date:
  ```bash
  TZ=Europe/London date +%m%d
  ```
  Carry on only if the result is **1115–1231** or **0101–0115**. Otherwise stop immediately, with no message and no file. Inside the window, do the normal batch.
- **Daily 6am run** (the prompt says "DAILY"). Do the normal batch.

## 1. Set up (already done if you're reading this from /tmp/gift-message-cards)

```bash
cd /tmp && curl -sSfL https://codeload.github.com/SharonLeeDesign/gift-message-cards/tar.gz/refs/heads/main | tar xz \
  && rm -rf gift-message-cards && mv gift-message-cards-main gift-message-cards
python3 -c "import reportlab" 2>/dev/null || pip install --quiet reportlab
```

Fonts (`fonts/`) and the vine (`assets/vine.png`) are in the repo. Don't install or convert fonts.

## 2. Find orders waiting for a card

Shopify Flow ("Gift message to order note + tag (Click & Drop)") tags every new order that has a non-empty "Gift Message" with **`gift-message`**. The run's job is every order tagged `gift-message` but not yet `giftcard-printed`.

Use the Shopify GraphQL query tool.
- **Important:** pass `first: 50` both inside `variables` **and** as the tool's own top-level `first` argument. The tool otherwise caps results at 10. Do the same with `after` when paging.

```graphql
query PendingGiftCards($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      name
      createdAt
      note
      tags
      lineItems(first: 20) {
        nodes { title customAttributes { key value } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

Run it twice and merge the results, removing duplicates by `id`:
1. **Main query:** `"tag:gift-message AND tag_not:giftcard-printed"`.
2. **Safety net in case Flow ever misses one:** `"created_at:>=<3 days ago, YYYY-MM-DD> AND tag_not:giftcard-printed"`. Get the date with `TZ=Europe/London date -d '-3 days' +%Y-%m-%d`.

**Build the cards.** For each order:
- Look at every line item's `customAttributes` for `key == "Gift Message"`, with the `value` trimmed of spaces at each end.
- **Ignore empty values.** Most orders carry an empty Gift Message.
- Make **one card per different non-empty message** in the order. Usually that's one card. If an order has two items with different messages, make two cards, labelled e.g. `#1150 (1/2)` and `#1150 (2/2)`.
- Skip orders with no non-empty message. Don't tag them.

**If there are no cards, stop now.** Send no file and no message, and keep your final reply to one line such as "Nothing to print." Michael doesn't want "nothing to print" notifications.

## 3. Make the PDF

Write `/tmp/gift-message-cards/batch.json`:
```json
[{"order": "#1150", "message": "..."}, {"order": "#1151", "message": "..."}]
```
Use the order's `name` (e.g. `#1150`) and the trimmed message, oldest order first. Then run:
```bash
mkdir -p /mnt/user-data/outputs
cd /tmp/gift-message-cards && python3 generate_gift_cards.py --input batch.json \
  --output "/mnt/user-data/outputs/Gift_Messages_$(TZ=Europe/London date +%Y-%m-%d_%H%M).pdf"
```
Keep any lines starting `WARNING:`. They go in the caption (step 4).

## 4. Send it

Call SendUserFile with the PDF:
- **Status:** `proactive` for scheduled runs; `normal` for ad-hoc or chat requests.
- **Caption:** short, listing the cards. For example: "Gift cards to print, 2 cards: #1150 (Tyneside), #1151 (Brighton)." Add one short line for each `WARNING:`, such as "#1151's message is very long, so check the card."

## 5. Mark the orders done

For each order that has a card in the PDF you just sent:

1. **Tag it** so it's never picked up again. Skip this if it already has the tag:
   ```graphql
   mutation TagPrinted($id: ID!, $tags: [String!]!) {
     tagsAdd(id: $id, tags: $tags) { node { id } userErrors { field message } }
   }
   ```
   with `{"id": "<order gid>", "tags": ["giftcard-printed"]}`.

2. **Fill in the Click & Drop note, but only if it's empty.** If the order's `note` is null or empty (Flow normally fills it in, so this is a safety net), write it so Royal Mail Click & Drop shows the message:
   ```graphql
   mutation BackfillNote($id: ID!, $note: String!) {
     orderUpdate(input: {id: $id, note: $note}) { order { id } userErrors { field message } }
   }
   ```
   Use one line per message: `<line item title> - Gift message: <message>`.
   **Never overwrite a note that already has text in it.**

## Rules

- Only tag orders that are actually in the PDF you sent.
- Don't change the Shopify theme or the Flow workflow.
- If a Shopify call fails, send one short message saying what failed. Don't retry over and over.
- Keep the final reply to one or two sentences.

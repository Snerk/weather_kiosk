# Put your project on the Hive kiosk

Anyone at Hive can publish a card to the lobby screen. No approval needed —
a robot checks your PR and merges it automatically. Live within ~15 minutes.

## The 4-minute version (works from any laptop or phone browser)

1. Make a free account at github.com if you don't have one.
2. Go to **github.com/Snerk/weather_kiosk** and press **Fork**.
3. In *your* fork, navigate to `content/residents/`, press
   **Add file → Create new file**, and name it
   `your-name/card.html` (the slash creates the folder).
4. Paste your HTML (see `_example/card.html` for a starting point).
   Optionally add `your-name/card.json`:
   ```json
   {"title": "My Startup", "author": "Your Name"}
   ```
5. Commit, then press **Contribute → Open pull request → Create pull request**.
6. Checks run (~1 min). If they pass, the bot merges and the kiosk pulls it in
   on its next update cycle.

## Rules the robot enforces

- Files only under `content/residents/your-name/`
- Types: html, css, md, json, png, jpg, gif, svg, webp
- ≤ 2 MB per file, ≤ 10 MB per PR
- No `<script>` — it wouldn't run anyway (the kiosk renders your card in a
  fully sandboxed iframe), so design with plain HTML + CSS.

Your card renders at roughly **1000 × 1450 px, portrait**. Big type reads best.
Be kind: it's a shared lobby screen.

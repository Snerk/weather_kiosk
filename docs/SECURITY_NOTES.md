# Security notes — read before going live

## Discord: use a bot, not a "generic account"

The original spec asked for a generic Discord *user* account. Automating a user
account (self-botting) violates Discord's Terms of Service and reliably gets
accounts — and sometimes servers — banned. The kiosk uses the sanctioned path
instead:

1. discord.com/developers/applications → **New Application** → Bot tab.
2. Copy the **bot token** into `/etc/weather-kiosk/secrets.env` as
   `DISCORD_BOT_TOKEN`.
3. OAuth2 → URL Generator → scope `bot`, permissions **View Channels** +
   **Read Message History** only. Open the URL and invite it to the Hive
   server (needs a server admin, once).
4. In each channel the kiosk should read, make sure the bot's role can view it.

The fetcher polls REST every 10 minutes — no gateway connection, no message
content beyond display, read-only permissions. Note the spec listed channel
`1123265586860916786` twice; the config deduplicates it, so add the intended
fourth channel ID to `kiosk/config.yaml` when you have it. Also confirm the
alert channel ID — the spec reuses `…4519594` as both a feed channel and the
alert channel, which the config currently reflects.

Privacy: this puts residents' Discord messages on a lobby screen. Announce it
in the server and keep the fed channels to ones residents expect to be public.

## Showcase: open contribution without open season

"Anyone can publish without approval" is handled with three stacked layers:

1. **CI gate** (`.github/workflows/showcase-automerge.yml`): auto-merge only
   when every changed file is under `content/residents/`, has an allowed
   extension, fits size caps, and contains no script content. Anything else
   waits for Snerk.
2. **Server path containment**: the kiosk only serves files under
   `content/residents/`, with path-traversal checks.
3. **Browser sandbox**: cards render in `<iframe sandbox="">` — the maximally
   restrictive sandbox. No scripts, no navigation, no forms, no popups, no
   same-origin access. Even if a malicious HTML file slipped through CI, it's
   inert pixels.

What CI *can't* judge is content (offensive images, ads for scams). The
mitigation is social + `git revert`: everything is attributed to a GitHub
account, and rollback is one commit. If that's not enough, flip the workflow's
merge step to add a label instead, making it approval-required.

One GitHub-specific caution: the workflow uses `pull_request_target` so it can
merge, but it checks out the PR head **only to inspect files, never to execute
them**. Don't add steps that run contributor code (npm install, pytest, etc.)
to this workflow.

## Admin panel

- Password is PBKDF2-hashed in `/etc/weather-kiosk/secrets.env`; never in the
  repo. Login attempts are rate-limited by a 1 s delay.
- The server binds to **127.0.0.1 only**, so the panel is reachable only from
  the kiosk's own keyboard (plug one in, type the key sequence). If you ever
  bind it to the LAN, put it behind HTTPS and change the password first.
- Privileged actions go through `bin/kiosk-syshelper` with a sudoers rule
  scoped to exactly that script.

## Update channel = attack surface

Anyone who can push to `main` owns the kiosk (it hard-resets to `origin/main`
and runs the code). Protect your GitHub account with a passkey/2FA, block
force pushes on `main`, and never merge code PRs you haven't read. This is the
single most important control in the whole system.

## Also worth knowing

- Something on this box is already listening on port 80 and SSH is open —
  audit both. The kiosk itself uses 8080/localhost.
- The BIOS is from 2022 (1.24.0); Dell has shipped OptiPlex 7060 firmware
  updates since. `fwupdmgr refresh && fwupdmgr update` on a maintenance visit.

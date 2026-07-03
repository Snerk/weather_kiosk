# Contributing from anywhere, on any device

You own `Snerk/weather_kiosk`. The kiosk tracks `origin/main` and self-updates
every 15 minutes. So the whole workflow is: **get a change onto `main`, from
wherever you are, and the kiosk takes care of the rest.** Git is already
decentralized — every clone is a full copy — you just need `main` on GitHub to
be the single source of truth, and to never edit code directly on the kiosk box.

## One-time setup

### Make the repo public
GitHub → your repo → **Settings → General → Danger Zone → Change visibility →
Public**.

### Protect yourself from force-push accidents (recommended)
**Settings → Branches → Add branch ruleset** on `main`: enable
"Require status checks to pass" is optional for a solo repo, but at minimum
enable "Block force pushes."

### Authenticate each device once
On any laptop you'll code from:

```bash
sudo apt install gh git        # or: brew install gh
gh auth login                  # browser flow; pick HTTPS
git config --global user.name  "Snerk"
git config --global user.email "you@example.com"
```

`gh auth login` stores a credential so `git push` just works — no SSH key
juggling per machine. On a phone or borrowed computer, skip all of this and use
the **github.com web editor** (see below).

## The everyday loop (any laptop)

```bash
# first time on this machine
gh repo clone Snerk/weather_kiosk && cd weather_kiosk

# every session
git pull --rebase origin main        # sync before you start — always
git switch -c fix/goes-stride        # small branch per change
# ...edit...
git add -A && git commit -m "goes: 20-min frame stride"
git push -u origin fix/goes-stride
gh pr create --fill                  # open a PR against main
gh pr merge --squash --delete-branch # merge it (you're the owner)
```

Why branches + PRs when you could push straight to `main`? Because the kiosk
deploys `main` automatically. The PR step is your only "staging area" — CI can
run, you can eyeball the diff on your phone, and a broken push doesn't take the
lobby screen down. When a change is trivial, pushing to `main` directly is
fine; just know it goes live in ≤15 min.

## From a phone / random computer (no git installed)

1. github.com → your repo → find the file → pencil icon → edit → **Commit
   changes**. Choose "Create a new branch and start a PR" for anything risky.
2. For bigger edits, press `.` (period) on the repo page or change the URL to
   `github.dev/Snerk/weather_kiosk` — full VS Code in the browser, commits
   push straight to GitHub. Works on a tablet.
3. **Codespaces** (Code → Codespaces → Create) gives you a real Linux shell in
   the browser if you need to run/test anything. Free tier is plenty.

All three routes end the same way: a commit lands on `main`, the kiosk pulls it.

## The kiosk box is a consumer, not a workstation

The updater runs `git reset --hard origin/main`, so **any local edits on the
kiosk are silently destroyed within 15 minutes**. That's a feature: the box
can never drift from the repo. If you're debugging on-site, either commit from
the box (`git switch -c`, push, merge from your phone) or expect your changes
to vanish. Secrets (`/etc/weather-kiosk/`) and cache (`/var/lib/weather-kiosk/`)
live outside the repo and survive every update.

## Rolling back a bad deploy

```bash
git revert <bad-commit> && git push origin main
```
Kiosk recovers on the next 15-minute tick — or immediately via the admin
panel's "Pull latest code now."

## Resident showcase PRs

PRs that only touch `content/residents/**` are validated and merged by the
GitHub Action with **no approval from you** (that's by design — see
`content/HOW_TO_POST.md` and `docs/SECURITY_NOTES.md`). Anything touching code
waits for you like a normal PR.

# Meeting guest bots

Headless Chromium guests that open a meeting link, complete the guest join form,
and stay connected. Yandex Telemost and Kontur.Talk are supported; the join
engine is provider-neutral, so another service can be added with one file.

## What changed for Telemost

After the Telemost/Messenger merge, the guest form is no longer in the top-level
document: it is rendered in an embedded `telemost.yandex.ru/private-join/...`
frame. The launcher now:

- searches every frame and prefers the embedded join frame;
- handles "Continue in browser" and dismisses onboarding/device dialogs;
- fills the guest name, switches the fake microphone and camera off, and clicks
  **Подключиться** / **Join**;
- recognises the waiting room and in-meeting controls as a successful join;
- if the embedded form is stuck after repeated clicks, reopens the same join
  frame directly with `mic=off&camera=off` as a same-tab fallback;
- reports invalid or finished meetings instead of waiting for the full timeout.

Chromium starts with fake capture devices backed by a generated silent WAV and a
black Y4M frame (`.cache/media/`). No real camera or microphone is touched and
no permission prompt blocks the form.

## Installation

Requires Linux, Python 3.10+, and enough memory for the active meeting pages.
Run from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If Playwright is missing from the current interpreter, the launcher retries
with `.venv/bin/python` when it exists, preserving the selected service.

## Usage

```bash
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 15 --workers 3
python main.py 'https://YOUR_DOMAIN.ktalk.ru/YOUR_EVENT' --count 15 --workers 3
```

Service selection follows this order:

1. Explicit `--service telemost` or `--service ktalk`.
2. URL hostname from the provider registry (`telemost.yandex.ru`,
   `telemost.yandex.com`, `telemost.360.yandex.ru`, `ktalk.ru`, or a subdomain of
   `ktalk.ru`).
3. Entry point fallback: `telemost.py` selects Telemost and `ktalk.py` selects
   kTalk for unrecognized domains. `main.py` instead exits with an argument error.

All entry points accept the same options. Supply a full `http://` or `https://`
guest URL; use the HTTPS link provided by the meeting service.

```bash
# Custom domain: choose the provider explicitly.
python main.py 'https://meet.example.org/EVENT' --service ktalk

# Russian random names, or one fixed name for every guest.
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --name-language ru
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --name 'Общий гость'

# Show the browser with images loaded.
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 1 --headed --load-images

# Close automatically after all join attempts finish.
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 2 --close
```

Successful sessions stay open by default. After all attempts finish, press
**Enter** to close them. **Ctrl+C** also cancels pending attempts and closes the
browser. Use `--close` for runs without interactive input.

## Arguments and options

| Argument / option | Default | Description |
| --- | --- | --- |
| `url` | Required | Full meeting or event URL. |
| `-h`, `--help` | — | Show help and exit. |
| `--service {telemost,ktalk}` | URL detection / entry point fallback | Override the provider. |
| `-n`, `--count COUNT` | `15` | Total guest sessions; positive integer. |
| `--name-language {ru,en}` | `en` | Random-name language; ignored with `--name`. Russian surnames match the first name's grammatical gender. |
| `--name NAME` | Random names | Same name for every guest; surrounding whitespace is stripped and an empty name is rejected. |
| `--workers WORKERS` | `3` | Maximum concurrent join attempts; positive integer, capped at the guest count. |
| `--delay DELAY` | `0` | Minimum interval between starting attempts across all workers, in seconds; finite non-negative number. |
| `--timeout TIMEOUT` | `30` | Browser launch and per-action timeout in seconds; positive integer. |
| `--join-timeout JOIN_TIMEOUT` | `180` | Maximum seconds spent on one guest's join form before the guest is marked failed. |
| `--headed` | Off | Show the browser. |
| `--load-images` | Off | Allow image requests. |
| `--chrome-binary CHROME_BINARY` | Playwright Chromium | Path to a Chrome/Chromium executable. |
| `--close` | Off | Close sessions after all attempts finish. |

Run `python main.py --help` for CLI help.

## Results and limitations

Logs include timestamps and, for guest-specific actions, guest numbers. Output
is flushed immediately. Failed guests are closed while other attempts continue.
When possible, failures save screenshots to `errors/SERVICE-guest-N.png` in the
project directory; later failures for the same service and guest number overwrite
that file. Screenshots, fake-media files, and Python/tool caches are ignored by
Git.

| Exit code | Meaning |
| --- | --- |
| `0` | Every guest completed the join form, or help was displayed. |
| `1` | At least one guest failed, or a browser/runtime error occurred. |
| `2` | Invalid arguments or a missing Python dependency. |
| `130` | Ctrl+C, or end-of-input while waiting for Enter. |

A join means the pre-join form closed, the waiting room appeared, or in-meeting
controls were detected. It does not prove the organizer admitted the guest or
that the remote side receives media. Screenshots and selectors follow the
English and Russian UI labels.

Each guest has independent cookies and local storage. `--workers` limits startup
concurrency, not the number of sessions kept open. Pages and incoming WebRTC
media still consume CPU and memory in headless mode. Service workers are disabled;
a browser crash affects all guests.

## Adding another meeting service

The launcher has no provider-specific code. A provider is one `Service` instance:

1. Create `services/my_service.py` and describe the UI:

   ```python
   from .base import Service

   MY_SERVICE = Service(
       key="my_service",
       label="My Meeting",
       hosts=("meet.example.com", "*.meet.example.com"),
       name_inputs=(("css selector", "input[name='guest']"),),
       join_buttons=(("css selector", "button[type='submit']"),),
       # Optional: continue_buttons, overlay_buttons, mic_off_buttons,
       # camera_off_buttons, joined_buttons, joined_markers,
       # failure_markers, frame_url_patterns, direct_frame_params.
   )
   ```

2. Register it in `services/__init__.py`:

   ```python
   from .my_service import MY_SERVICE

   SERVICES = {service.key: service for service in (TELEMOST, KTALK, MY_SERVICE)}
   ```

3. Run with the URL or `--service my_service`. URL detection, frame search,
   overlays, device switching, the fallback path, screenshots, and CLI choices
   work automatically.

`services/base.py` documents every field. Locators are `(strategy, selector)`
pairs and are tried in order; put stable test IDs before text fallbacks. Markers
are case-insensitive substrings of the rendered page text. `*.` host patterns
match subdomains only, so list the bare domain separately. `frame_url_patterns`
plus `direct_frame_params` enable the same-tab direct-frame fallback for services
that embed their join form.

## Development

- `main.py`: unified CLI; `telemost.py` and `ktalk.py`: provider fallback entry points.
- `launcher.py`: arguments, names, browser lifecycle, frame-aware join engine, workers, cleanup.
- `services/`: provider registry — `base.py`, `telemost.py`, `ktalk.py`.
- `media.py`: fake camera/microphone assets.
- `test_*.py`: offline tests with a state-machine fake browser; no real meetings.

```bash
python -m unittest -v
```

Optional checks with Ruff installed:

```bash
ruff check .
ruff format --check .
```

Tests do not join meetings; real-meeting behavior requires separate validation.

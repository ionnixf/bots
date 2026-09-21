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
2. URL hostname: `telemost.yandex.ru`, `telemost.yandex.com`, `ktalk.ru`, or a
   subdomain of `ktalk.ru`.
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
| `--timeout TIMEOUT` | `30` | Browser launch and per-action timeout in seconds; positive integer, not a total run limit. Error screenshots use a separate 5-second timeout. |
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
that file. Screenshots and Python/tool caches are ignored by Git.

| Exit code | Meaning |
| --- | --- |
| `0` | Every guest completed the join form, or help was displayed. |
| `1` | At least one guest failed, or a browser/runtime error occurred. |
| `2` | Invalid arguments or a missing Python dependency. |
| `130` | Ctrl+C, or end-of-input while waiting for Enter. |

Join-form disappearance is the completion signal. It does not prove admission
by the organizer or reception of audio/video. The selectors support English and
Russian UI labels; Telemost also handles the optional "Continue in browser"
screen and device warnings.

Each guest has independent cookies and local storage. `--workers` limits startup
concurrency, not the number of sessions kept open. Pages and incoming WebRTC
media still consume CPU and memory in headless mode. Service workers are disabled;
a browser crash affects all guests.

## Development

- `main.py`: unified CLI; `telemost.py` and `ktalk.py`: provider fallback entry points.
- `launcher.py`: arguments, names, browser lifecycle, workers, and cleanup.
- `services.py`: provider detection and selectors.
- `test_*.py`: offline tests with mocked browser operations.

```bash
python -m unittest -v
```

Optional checks with Ruff installed:

```bash
ruff check .
ruff format --check .
```

Tests do not join meetings; real-meeting behavior requires separate validation.

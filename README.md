# Meeting Guest Launcher — Telemost & Kontur.Talk

A single Python CLI for Yandex Telemost and Kontur.Talk (kTalk), using
Playwright. One Chromium browser hosts isolated guest contexts,
with a configurable number of concurrent join attempts.

The browser runs headless by default. Camera and microphone permissions are
denied before navigation, audio output is muted, and image loading is blocked.
Guest names are randomly selected in English by default. Use
`--name-language ru` for Russian names with matching surname gender, or pass
`--name` to use one specified name for every guest.

## Requirements

- Linux with Python 3.10 or newer. Interactive Enter handling uses the Linux
  asyncio event loop.
- Playwright and its Chromium browser, installed with the commands below.
- Enough memory for the requested number of active meeting pages.

## Installation

Run these commands from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Playwright downloads its browser separately from the Python package. No
Selenium or ChromeDriver installation is needed. If Playwright is missing from
the current interpreter, the launcher retries with the project's
`.venv/bin/python` when available, preserving the selected service.

## Usage

The service is detected automatically from the URL. Both commands accept the
same options:

```bash
python main.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 15 --workers 3
python main.py 'https://YOUR_DOMAIN.ktalk.ru/YOUR_EVENT' --count 15 --workers 3
```

Detection recognizes `telemost.yandex.ru`, `telemost.yandex.com`, `ktalk.ru`,
and subdomains of `ktalk.ru`. For a custom domain or an explicit override, use
`--service telemost` or `--service ktalk`.

Convenience entry points also detect the service from the URL, falling back to
their respective service for unrecognized domains:

```bash
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 15 --workers 3
python ktalk.py 'https://YOUR_DOMAIN.ktalk.ru/YOUR_EVENT' --count 15 --workers 3
```

The URL is required. If `main.py` cannot recognize its domain, it asks for
`--service` before launching the browser. Pass the full guest URL, including
`https://`.
All examples below also work with `ktalk.py` and a kTalk event URL.

Migration: the former kTalk-only copy used `telemost.py` as an alias for
kTalk. In this combined project, `telemost.py` means Yandex Telemost;
use `ktalk.py` or `main.py --service ktalk` for Kontur.Talk.

Successful sessions stay open after joining. Press **Enter** or **Ctrl+C** to
close them. Ctrl+C cancels pending work and closes the browser and its contexts.
For a short connection check that closes everything automatically:

```bash
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 2 --close
```

To inspect the browser visually:

```bash
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --headed --load-images
```

## Options

Choose the language of guest names:

```bash
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --name-language ru
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --name-language en
```

Use the same specified name for every guest:

```bash
python telemost.py 'https://telemost.yandex.ru/j/YOUR_MEETING_ID' --count 15 --name 'Общий гость'
```

Omit `--name` to return to random names. `--name-language` only affects the
random-name mode.

| Option | Default | Description |
| --- | --- | --- |
| `--service` | Detected from URL | Override with `telemost` or `ktalk`; convenience scripts provide a fallback for custom domains. |
| `url` | Required | Meeting to join. |
| `-n`, `--count` | `15` | Total guest sessions. |
| `--name-language` | `en` | Guest name language: `ru` or `en`. |
| `--name` | Random names | Use the same specified name for every guest session. |
| `--workers` | `3` | Maximum concurrent join attempts. Use `1` for sequential joins. |
| `--delay` | `0` | Minimum interval between starting join attempts, in seconds. |
| `--timeout` | `30` | Browser launch and per-action timeout, in seconds; not a total run limit. |
| `--headed` | Off | Show browser windows. |
| `--load-images` | Off | Allow image requests. |
| `--chrome-binary` | Playwright browser | Optional path to a Chrome/Chromium executable. |
| `--close` | Off | Close sessions after all join attempts finish. |

Use `python main.py --help` for command-line help. The old Selenium-only
`--webdriver-url` option has been removed.

## Logs and failures

Terminal messages include a timestamp and guest number. They describe context
creation, navigation, form interaction, warnings, errors, and cleanup. Output
is flushed immediately, including when redirected to a file.

Failed guests are closed without stopping other join attempts. When possible,
a screenshot is saved to `errors/SERVICE-guest-N.png`; a later failure for
the same guest number overwrites it. Generated screenshots and Python/tool
caches are ignored by Git.

Exit codes:

- `0`: every guest completed the join form.
- `1`: at least one guest failed, or a browser/runtime error occurred.
- `2`: invalid command-line arguments or a missing Python dependency.
- `130`: interrupted with Ctrl+C or end-of-input while waiting for Enter.

## Performance and limitations

Each guest has independent cookies and local storage. Sharing one browser
avoids launching a complete browser for every guest, but pages and incoming
media still use CPU and memory. `--workers` limits simultaneous startup work;
it does not limit how many successful sessions remain open. Start with three
workers and reduce the count if the machine becomes overloaded.

Service workers are disabled so they cannot bypass image request blocking.
Headless mode does not disable incoming WebRTC media. A browser crash affects
all guest contexts.

The script handles both English and Russian meeting UI labels. Its own logs,
help text and documentation are English; guest names can be English or Russian.
Telemost handles the optional "Continue in browser" screen and device warnings.
kTalk uses the anonymous authorization form and its stable test IDs.

Disappearance of the join form is used as a completion signal. It does not
prove admission by the organizer or reception of audio/video. Unit tests cover
service selection, mocked join flows, concurrency, cancellation, and failure
cleanup. Real-meeting behavior still requires validation.

## Development

- `main.py`: unified command; `telemost.py` and `ktalk.py`: convenience commands.
- `launcher.py`: shared arguments, names, browser lifecycle, workers, and cleanup.
- `services.py`: provider-specific selectors.
- `test_*.py`: offline regression tests.

```bash
python -m unittest -v
```

Optional formatting and lint checks, with Ruff installed:

```bash
ruff check .
ruff format --check .
```

The unit tests use mocked browser operations and do not join any meeting.

## About this fork

This is [Textual](https://github.com/Textualize/textual) 8.2.8 with work on speed and memory: fewer objects per widget, leaks fixed when widgets are removed, less layout work, and linear-time removal of `Tree` nodes and `DataTable` rows. The public API is the same as upstream's, apart from the `__slots__` caveat under [Compatibility](#compatibility).

### Measured gains

Upstream Textual 8.2.8 against this fork, each measurement in a fresh interpreter. Timings are the median of 5 runs after one warm-up run; memory figures are from one run.

| Workload | 3.12 upstream | 3.12 fork | 3.12 change | 3.14 upstream | 3.14 fork | 3.14 change |
|---|---:|---:|---:|---:|---:|---:|
| Demo app, traced memory (MB) | 24.7 MB | 21.8 MB | -11.7% | 27.9 MB | 25.1 MB | -10.0% |
| Demo app, peak RSS (MB) | 61.6 MB | 56.1 MB | -8.9% | 64.6 MB | 59.9 MB | -7.3% |
| Widget churn, retained memory (MB) | 4.2 MB | 0.2 MB | -95.7% | 4.1 MB | 0.1 MB | -98.2% |
| Startup to first frame (ms) | 98.8 ms | 89.0 ms | -9.9% | 91.0 ms | 87.8 ms | -3.5% |
| Resize, 2,000 widgets (ms) | 334.9 ms | 309.2 ms | -7.7% | 332.9 ms | 309.8 ms | -6.9% |
| Tree, remove 10,000 nodes (ms) | 269.2 ms | 23.7 ms | -91.2% | 299.2 ms | 23.5 ms | -92.2% |
| DataTable, remove 10,000 rows (ms) | 17251.6 ms | 80.5 ms | -99.5% | 19164.1 ms | 86.1 ms | -99.6% |

Apple M4, 16 GB, macOS 27.2.1, CPython 3.12.11 and 3.14.0. The tree workload removes 10,000 leaves from a single node; "widget churn" is memory still held after mounting and removing 1,000 widgets 20 times. Reproduce with `python3 tools/benchmark.py` (needs [uv](https://docs.astral.sh/uv/), nothing else); the workloads are in [`tools/benchmark.py`](tools/benchmark.py).

### Which Python versions

Gains can differ by Python version, so the table shows two. 3.14 is the newest stable release, the one this fork is tuned on, and the only one where `Styles` is slotted. 3.12 was expected to gain less, because from 3.12 CPython already stores most instance attributes compactly, so `__slots__` saves only about 16–32 bytes per object.

The measurements do not bear that out: on 3.12 memory is 9–12% lower and resize 8% faster, against 7–10% and 7% on 3.14. Startup is 10% faster on 3.12 but only 3.5% on 3.14, too small a gain to tell apart from run-to-run variation, which the table does not show. The leak and removal fixes cut retained memory and removal time by 91% or more on both. Python 3.9–3.11 are supported but not measured.

### Compatibility

`RenderStyles`, `Signal`, `BindingsMap` and `NodeList` (and `Styles` on Python 3.14+) use `__slots__`, so they no longer accept arbitrary attributes. Code that sets its own attributes on them will raise `AttributeError`. Everything else is meant to behave exactly like upstream.

### Install

There is no PyPI release. Install from this repository:

```bash
pip install git+https://github.com/gazorby/textual@next
```

---


[![Discord](https://img.shields.io/discord/1026214085173461072)](https://discord.gg/Enf6Z3qhVr)
[![Supported Python Versions](https://img.shields.io/pypi/pyversions/textual)](https://pypi.org/project/textual/)
[![PyPI version](https://badge.fury.io/py/textual.svg?)](https://badge.fury.io/py/textual)
![OS support](https://img.shields.io/badge/OS-macOS%20Linux%20Windows-red)



![textual-splash](https://github.com/user-attachments/assets/4caeb77e-48c0-4cf7-b14d-c53ded855ffd)

# Textual

<img align="right" width="250" alt="clock" src="https://github.com/user-attachments/assets/63e839c3-5b8e-478d-b78e-cf7647eb85e8" />

Build cross-platform user interfaces with a simple Python API. Run your apps in the terminal *or* a web browser.

Textual's API combines modern Python with the best of developments from the web world, for a lean app development experience.
De-coupled components and an advanced [testing](https://textual.textualize.io/guide/testing/) framework ensure you can maintain your app for the long-term.

Want some more examples? See the [examples](https://github.com/Textualize/textual/tree/main/examples) directory.

```python
"""
An App to show the current time.
"""

from datetime import datetime

from textual.app import App, ComposeResult
from textual.widgets import Digits


class ClockApp(App):
    CSS = """
    Screen { align: center middle; }
    Digits { width: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Digits("")

    def on_ready(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self) -> None:
        clock = datetime.now().time()
        self.query_one(Digits).update(f"{clock:%T}")


if __name__ == "__main__":
    app = ClockApp()
    app.run()
```

> [!TIP]
> Textual is an asynchronous framework under the hood. Which means you can integrate your apps with async libraries &mdash; if you want to.
> If you don't want or need to use async, Textual won't force it on you. 



<img src="https://img.spacergif.org/spacer.gif" width="1" height="64"/>

## Widgets

Textual's library of [widgets](https://textual.textualize.io/widget_gallery/) covers everything from buttons, tree controls, data tables, inputs, text areas, and more…
Combined with a flexible [layout](https://textual.textualize.io/how-to/design-a-layout/) system, you can realize any User Interface you need.

Predefined themes ensure your apps will look good out of the box. 


<table>

<tr>

  <td>
    
  ![buttons](https://github.com/user-attachments/assets/2ac26387-aaa3-41ed-bc00-7d488600343c)
    
  </td>

  <td>
    
![tree](https://github.com/user-attachments/assets/61ccd6e9-97ea-4918-8eda-3ee0f0d3770e)
    
  </td>
  
</tr>


<tr>

  <td>
    
  ![datatables](https://github.com/user-attachments/assets/3e1f9f7a-f965-4901-a114-3c188bd17695)
    
  </td>

  <td>
    
![inputs](https://github.com/user-attachments/assets/b02aa203-7c37-42da-a1bb-2cb244b7d0d3)
    
  </td>
  
</tr>
<tr>

<td>

![listview](https://github.com/user-attachments/assets/963603bc-aa07-4688-bd24-379962ece871)

</td>

<td>

![textarea](https://github.com/user-attachments/assets/cd4ba787-5519-40e2-8d86-8224e1b7e506)
  
</td>

  
</tr>

</table>


<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>

## Installing

Install Textual via pip:

```
pip install textual textual-dev
```

See [getting started](https://textual.textualize.io/getting_started/) for details.


<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>

## Demo


Run the following command to see a little of what Textual can do:

```
python -m textual
```

Or try the [textual demo](https://github.com/textualize/textual-demo) *without* installing (requires [uv](https://docs.astral.sh/uv/)):

```bash
uvx --python 3.12 textual-demo
```

<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>

## Dev Console

<img align="right" width="40%" alt="devtools" src="https://github.com/user-attachments/assets/12c60d65-e342-4b2f-9372-bae0459a7552" />


How do you debug an app in the terminal that is also running in the terminal?

The `textual-dev` package supplies a dev console that connects to your application from another terminal.
In addition to system messages and events, your logged messages and print statements will appear in the dev console.

See [the guide](https://textual.textualize.io/guide/devtools/) for other helpful tools provided by the `textual-dev` package.

<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>

## Command Palette


Textual apps have a *fuzzy search* command palette.
Hit `ctrl+p` to open the command palette.

It is easy to extend the command palette with [custom commands](https://textual.textualize.io/guide/command_palette/) for your application.


![Command Palette](https://github.com/user-attachments/assets/94d8ec5d-b668-4033-a5cb-bf820e1b8d60)

<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>

# Textual ❤️ Web

<img align="right" width="40%" alt="textual-serve" src="https://github.com/user-attachments/assets/a25820fb-87ae-433a-858b-ac3940169242">


Textual apps are equally at home in the browser as they are the terminal. Any Textual app may be served with `textual serve` &mdash; so you can share your creations on the web.
Here's how to serve the demo app:

```
textual serve "python -m textual"
```

In addition to serving your apps locally, you can serve apps with [Textual Web](https://github.com/Textualize/textual-web).

Textual Web's firewall-busting technology can serve an unlimited number of applications.

Since Textual apps have low system requirements, you can install them anywhere Python also runs. Turning any device into a connected device.
No desktop required!


<img src="https://img.spacergif.org/spacer.gif" width="1" height="32"/>


## Join us on Discord

Join the Textual developers and community on our [Discord Server](https://discord.gg/Enf6Z3qhVr).

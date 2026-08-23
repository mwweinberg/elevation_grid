# Elevation window

A 32x16 RGB LED matrix (Adafruit RGB Matrix + RTC HAT, product 3920) that acts
as a window drifting slowly across the world, showing the elevation of whatever
rectangle of the planet it is currently over. Ocean is blue (brighter = shallower),
land goes dim red -> red -> yellow with height.

The script is `elevation_window.py`. Everything else in this folder is history
(see the bottom of this file). For the reasoning behind the design, the
hardware assessment, and the list of open decisions, see `DESIGN.md`.

## How it works

Elevation is read directly from the ETOPO1 GeoTIFF at
`opentopodata/data/etopo1/ETOPO1.tif` (466 MB, 1 arc-minute, includes ocean
depth) using `rasterio`. **No server is needed.** The old design queried a
self-hosted opentopodata API one pixel at a time; reading the raster locally is
both simpler and roughly a thousand times faster (a whole 512-pixel frame
samples in about a millisecond on a laptop).

Output goes to the panel through hzeller's `rpi-rgb-led-matrix` Python bindings.
If that library isn't importable (e.g. you're on a laptop) the frame is drawn in
the terminal with ANSI colours instead, so you can develop anywhere.

The script also serves a small web page (port 80 on the Pi, so
`http://elevationgrid.local/` if the Pi is named `elevationgrid`) that mirrors
the panel live, shows the window's position on a world map, and draws a trail
of where it has been. The map is generated from ETOPO1 with the same colour
scheme as the panel and cached in `world_map_cache.npy` on first run. The page
polls once per `--interval`; there are no controls. `--no-web` disables it,
`--web-port 8080` lets it run without root on a laptop.

## Running on a laptop

    python3 -m venv venv && ./venv/bin/pip install rasterio numpy
    ./venv/bin/python elevation_window.py --interval 0.2 --start 27.9,86.9 --web-port 8080

then open http://localhost:8080/ for the web view.

## Running on the Pi

Step-by-step from a blank SD card: see `pi_install_instructions.md`.
Condensed version:

Works on Pi 1 / Zero / 2 / 3 / 4. **Not** Pi 5 (rpi-rgb-led-matrix does not
support its GPIO; you'd need Adafruit's `piomatter` instead).

1. Copy this folder, including `opentopodata/data/etopo1/ETOPO1.tif`, to the Pi.
2. Install the raster libraries. Use apt rather than pip so you don't compile
   GDAL on a Pi (piwheels doesn't reliably have rasterio for the armv6 Pi 1):

        sudo apt install python3-rasterio python3-numpy

3. Install the matrix library and its Python bindings, following
   https://github.com/hzeller/rpi-rgb-led-matrix (bindings/python). Adafruit's
   installer script also works:
   https://learn.adafruit.com/adafruit-rgb-matrix-plus-real-time-clock-hat-for-raspberry-pi/driving-matrices
   Either way you must disable onboard audio (`dtparam=audio=off` in
   `/boot/config.txt`) and run as root.
4. Run:

        sudo python3 elevation_window.py --slowdown 1

   `--slowdown` is `gpio_slowdown`: 0-1 for Pi 1/Zero, 2 for Pi 3, 4 for Pi 4.
   If the panel flickers or shows garbage, raise it. Add
   `--mapping adafruit-hat-pwm` if you soldered the HAT's GPIO4-GPIO18 jumper.

To start on boot, a systemd unit or a `@reboot` cron line pointing at that
command is enough.

## Tuning knobs (top of `elevation_window.py`)

- `DEG_PER_PIXEL` – latitude degrees per pixel (0.1 = the 32-px width covers
  ~350 km at mid-latitudes). Longitude spacing is stretched by 1/cos(lat) so
  pixels stay square on the ground. Below ~0.017 you're just oversampling ETOPO1.
- `STEP_DEG`, `--interval` – drift speed.
- `MIN_SPAN_M` – minimum relief the colour scale is stretched over, so a flat
  frame doesn't turn into noise.
- `MAX_BRIGHTNESS` – full-white LEDs are blinding indoors.
- `PANEL_FLIP_VERTICAL` / `PANEL_FLIP_HORIZONTAL` – physical panel orientation
  (the web page is always north-up; match the panel to it).
- Colours live in `elevation_to_rgb()`. The scale is anchored at sea level and
  adapts to each frame's max height/depth; swap in fixed constants there if you
  prefer stable colours over per-frame contrast.
- `TRAIL_LEN` – how many past positions the web page's trail keeps.
- `--start lat,lon` and `--heading` set where the window begins and which way
  it drifts. Longitude wraps across the date line; latitude bounces off the
  poles with a little random jitter so the path doesn't repeat.

## Ideas / v2

- Small e-paper display showing a world map with a dot/box for the window's
  current position. The web page already does this on screen; the e-paper
  version can reuse `ElevationRaster.world_map()` and the trail. Check which
  GPIO pins the matrix HAT leaves free before buying one (SPI displays may
  conflict).
- The HAT's RTC is currently unused; it could seed the start position from the
  date, or drive a "sunlight" tint.

---

## History

`elevation_grid.py`, `elevation_grid_relearn.py` and `elev_mat_test.py` are the
2021-2022 prototypes. They queried a self-hosted opentopodata server
(`http://localhost:5000/v1/etopo1?locations=...`) one pixel at a time. In
September 2023 that approach was abandoned because the opentopodata Docker
image did not build on a Raspberry Pi. The `opentopodata/` and
`open-elevation/` directories are the server checkouts from that attempt; only
the `ETOPO1.tif` inside `opentopodata/data/etopo1/` is still used.

Old notes, kept for reference: the server needed the etopo1 dataset added
(copy `/etopo1` into `/opentopodata/data`, copy `config.yaml` into
`/opentopodata`, `make build`, `make run`) or requests would fail with
`KeyError: 'results'`. See https://www.opentopodata.org/datasets/etopo1/.

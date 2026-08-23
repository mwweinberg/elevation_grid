# Design notes

Written August 2026 when the project was picked back up after stalling in
September 2023. This records the state of the project, the reasoning behind
the rewrite, and the decisions that were made (and the ones still open).
`README.md` tells you how to run it; this file tells you why it looks the
way it does.

## 1. The goal

A 32-wide by 16-tall RGB LED matrix, driven by a Raspberry Pi with the
Adafruit RGB Matrix + Real Time Clock HAT (product 3920), acts as a window
that drifts slowly across the world. Each LED shows the elevation of one point
of the rectangle of Earth currently under the window. A possible v2 adds a
small e-paper display with a world map and a marker for the window's position.

## 2. State of the project in 2023

- Three prototype scripts (`elevation_grid.py`, `elevation_grid_relearn.py`,
  `elev_mat_test.py`) built a list of lat/lon points, queried an elevation
  API for each one, converted the results to colours, and moved the frame.
- Elevation came from a self-hosted **opentopodata** server
  (`http://localhost:5000/v1/etopo1?locations=lat,lon`) with the ETOPO1
  dataset. An **open-elevation** checkout with SRTM tiles was also tried.
- The scripts only ever ran with a 3x3 test grid and made **one HTTP request
  per pixel**, sleeping 0.1 s between requests (a leftover from public-API rate
  limits). Scaled to 512 pixels that would have been ~50 s per frame.
- The matrix output was never written; the scripts only printed the colour
  lists.
- The project stopped because the opentopodata Docker image would not build
  on the Raspberry Pi.

## 3. The key realisation: no server is needed

The server only ever answered "what is the elevation at (lat, lon)?", and the
answer was already on disk: `opentopodata/data/etopo1/ETOPO1.tif` is the
complete ETOPO1 dataset as a 466 MB GeoTIFF (21601 x 10801 int16, EPSG:4326,
1 arc-minute ≈ 1.85 km per cell, includes ocean bathymetry).

Python's `rasterio` (a thin wrapper over GDAL) can open that file and sample
arbitrary coordinates directly. That removes Docker, Flask, HTTP, and the build
problem entirely, and it is orders of magnitude faster: a full 16x32 frame
samples in well under a millisecond on a laptop, versus tens of seconds via
per-pixel HTTP. The speed change matters for the design as much as the
simplicity: frame rate is no longer dictated by API latency, so the window can
crawl smoothly instead of jumping.

Alternatives considered and rejected:

| Option | Why not |
|---|---|
| Public opentopodata API (batch 100 points/request) | 1,000 requests/day cap ≈ 160 frames/day, needs network, and the display would die when the internet did. |
| Retry the Docker build on ARM | Solves a problem we no longer have. |
| Load the whole raster into RAM as a numpy array | 466 MB; fine on a Pi 4, not on a Pi 1 (512 MB total). rasterio's windowed reads are fast enough that it isn't needed. |

## 4. Hardware assessment

- A 16x32 HUB75 panel on the Adafruit HAT is the textbook use case for
  hzeller's `rpi-rgb-led-matrix` library, which has Python bindings and an
  `adafruit-hat` GPIO mapping. A panel this small is trivial load for any Pi,
  including an original Pi 1 (which is what the library was first written for).
- **Constraint: `rpi-rgb-led-matrix` does not work on a Raspberry Pi 5**
  (different GPIO architecture). Pi 5 would need Adafruit's `piomatter` instead.
- Requirements on the Pi: onboard audio disabled (`dtparam=audio=off`), run as
  root, and a `gpio_slowdown` value matched to the Pi generation (0-1 for Pi 1
  / Zero, 2 for Pi 3, 4 for Pi 4).
- The HAT's real-time clock is unused by the current design.
- Installing rasterio: on armv6 (Pi 1 / Zero) pip may not find a wheel and
  would try to compile GDAL. Use `apt install python3-rasterio python3-numpy`.

### Development on a Pi 3, deployment on a Pi 1

Plan (Aug 2026): set up and debug on a Pi 3 Model B v1.2 (Wi-Fi, SSH), then
move to an original Model B for the final build. Findings:

- **The original Model B (2012-13, rev 1 and rev 2) has a 26-pin header. HATs
  need 40 pins, which arrived with the Model B+ (2014).** The Adafruit HAT
  drives the panel through GPIOs 5, 6, 12, 13, 16, 19, 20, 21 and 26, which
  do not exist on the 26-pin header, so an adapter cannot fix it. Check the
  pin count before planning around the old board; a B+ or Pi Zero works, a
  26-pin B does not. Rev 1 of the original B also has only 256 MB RAM (ok for
  this script, which never loads the whole raster).
- **Use 32-bit Raspberry Pi OS on the Pi 3.** It is built for ARMv6 and runs
  on every Pi from the original to the 4, so the finished SD card can simply
  move to the Pi 1: apt-installed rasterio/numpy and the runtime-detecting
  rpi-rgb-led-matrix library carry over unchanged. A 64-bit image would
  require redoing the setup on the (much slower) Pi 1.
- Per-board differences are small: `--slowdown 2` on the Pi 3 vs 0-1 on the
  Pi 1; the Pi 1 is single-core so raise `--interval` if the panel flickers;
  Ethernet-only SSH on the Pi 1; frame sampling ~20-50 ms instead of ~1 ms,
  which is irrelevant at a 1 s frame interval.
- **Outcome: the old board turned out to be a 26-pin Model B, so it is out.**
  Cheapest replacement if a small final build is wanted: Raspberry Pi Zero
  2 W (~$15; buy the "2 WH" with the header pre-soldered). Same Cortex-A53 as
  the Pi 3, so the Pi 3's SD card boots on it unchanged with the same
  `--slowdown`. The full-size HAT overhangs a Zero but works electrically;
  Adafruit's RGB Matrix Bonnet (3211) is the Zero-sized equivalent (no RTC).
  Otherwise the Pi 3 itself is a fine permanent home.
- **Microcontroller instead (Pi Pico)?** Possible but a separate project:
  the RP2040 drives HUB75 well via PIO (Protomatter / CircuitPython
  `rgbmatrix`), but the Pi HAT can't be used (hand-wire the panel or use a
  Pimoroni Interstate 75 / Adafruit MatrixPortal S3), the 466 MB GeoTIFF must
  be preprocessed on a laptop into a ~2-13 MB packed global raster (8-bit
  quantised or an SD card), and the script is rewritten in CircuitPython
  without rasterio/numpy. Worth it only for the instant-on, no-OS gadget
  appeal; if the aim is just cheap/small, the Zero 2 W is far less work.
  If going embedded, the MatrixPortal S3 (8 MB flash, plugs straight onto the
  panel) fits this project better than a bare Pico.

## 5. Decisions made

1. **Data access: direct raster reads with rasterio.** No server of any kind.
   The `opentopodata/` and `open-elevation/` directories are kept only because
   the `.tif` lives inside one of them; they could be reduced to just that file.
2. **Target Pi: something older than a Pi 5, possibly an original Pi 1.**
   Therefore `rpi-rgb-led-matrix`, apt-installed rasterio, and a design that
   never loads the whole raster into memory.
3. **Single script.** `elevation_window.py` does raster sampling, colour
   mapping, motion, and output. A terminal renderer is the fallback when
   `rgbmatrix` isn't importable, so development happens on a laptop and the
   same file runs unchanged on the Pi.

## 6. Design details and their rationale

**Window geometry.** The frame is defined by its centre, not its top-left
corner (the prototypes used top-left; centre makes bouncing and wrapping
symmetric). `DEG_PER_PIXEL` sets latitude degrees per pixel; longitude spacing
is divided by cos(latitude) so pixels stay roughly square on the ground rather
than compressing toward the poles. The prototypes' increments (0.256° lat vs
0.0128° lon) were test values that gave pixels 20x taller than wide.
The default 0.1°/pixel makes the 32-pixel width about 350 km at mid-latitudes,
which shows regional terrain. Going below ~0.017°/pixel just oversamples
ETOPO1's native resolution.

**Motion.** The window moves along a heading vector by `STEP_DEG` per tick.
Longitude wraps across the date line (the prototypes bounced at ±179°, which
is wrong for a globe). Latitude bounces off the poles, and the heading gets a
small random jitter on each bounce so the path never repeats exactly — that
idea is carried over from the prototypes.

**Sampling.** Points are converted to raster row/column with the GeoTIFF's
affine transform; columns are taken modulo the raster width so a window
straddling the date line still reads correctly. The file is stripped
(one row per block), so the code reads the band of rows the frame covers and
fancy-indexes the needed columns.

**Colour.** The prototypes' scheme is kept: blue underwater, land ramps red
then spills into green to make yellow. Two changes:

- Sea level is a fixed anchor and the scale above/below it adapts to the
  current frame's max height and depth. Pure per-frame min/max (the prototype
  approach) gives maximum contrast but makes the same mountain change colour
  as the window drifts; a fixed global scale is stable but makes flat regions
  a dark smear. This is the middle path. Swapping in fixed constants is a
  one-line change in `elevation_to_rgb()` if stable colours turn out to look
  better on the real panel.
- `MIN_SPAN_M` floors the relief the scale is stretched over, so a completely
  flat frame does not divide by zero (the prototype's `remap_values` would
  have) or turn a few metres of noise into a rainbow.

Because ETOPO1 includes bathymetry, the ocean is a real depth gradient rather
than a flat blue; SRTM-based data (as in `open-elevation/`) would not give that.

**Brightness.** `MAX_BRIGHTNESS` scales all colours down from 255; a small
panel at full white is uncomfortable indoors.

**Live web page (added Aug 2026).** Until the e-paper v2 exists, the Pi
serves `http://elevationgrid.local/`: a mirror of the panel, the centre
coordinates, and a world map with the window drawn as a box plus a trail of
recent positions. Design choices:

- Same process as the panel loop, a `ThreadingHTTPServer` from the standard
  library in a daemon thread — no Flask, no extra packages, nothing for the
  service unit to coordinate. The HTTP thread only reads a snapshot the main
  loop publishes under a lock, so it can never stall the panel.
- Two JSON endpoints: `state.json` (position, heading, the 16x32 frame as hex
  rows, the trail) polled once per `--interval`, and `map.json` fetched once.
- The world map is ETOPO1 itself, downsampled to 360x180 with
  `rasterio`'s `out_shape` averaging and coloured with the panel's own
  `elevation_to_rgb()`. This avoids shipping an image asset and keeps the page
  visually consistent with the panel. Reading the whole GeoTIFF takes up to a
  minute on a Pi 3, so the result is cached to `world_map_cache.npy` (260 KB).
- No controls, by decision; the page is a viewer.
- Port 80 because the script already runs as root for GPIO; `--web-port`
  exists for laptop use. Hostname `elevationgrid` + Pi OS's default avahi
  gives the `.local` address with no further setup.
- The e-paper v2 can reuse `world_map()` and the trail directly.

## 7. Open decisions / things to try on the real panel

- Degrees per pixel: 0.1 is a guess. Whole mountain ranges vs. single valleys
  is an aesthetic choice that needs the physical panel to judge.
- Adaptive vs. fixed colour scale (see above).
- Drift speed and whether to move sub-pixel amounts per tick for smoother motion.
- Whether the RTC should do anything (seed a start position from the date,
  tint by local time of day, etc.).
- v2 e-paper map: check which GPIO pins the matrix HAT leaves free before
  choosing a display, since SPI/I2C pins may be in use.

## 8. Verification done so far (laptop only)

- Known points sample correctly: New York ≈ -11 m (ETOPO1 cell average),
  Everest area 8,271 m, mid-Pacific -4,528 m.
- Windows centred near Everest, on the date line (-179.9°), and at 89.5° N
  all produce sensible frames; the pole case reverses heading as expected.
- Flat frames (mid-ocean, Kansas) render without error.
- ~0.65 ms per frame for sampling on a desktop; even 100x slower on a Pi 1
  is far below the 1 s default frame interval.
- Web page: `/`, `/state.json`, `/map.json` and a 404 path all respond
  correctly on a laptop; the rendered world map has the right orientation
  (Tibet/Andes/Antarctica where expected, ocean ridges visible).
- On the Pi 3 (Raspbian Trixie 32-bit, Aug 23 2026): rasterio sampling gives
  identical results to the laptop; the world-map build takes ~1 minute on
  first run and is then cached; the web page serves on port 80 and is
  reachable as http://elevationgrid.local/ from the LAN; the systemd service
  starts on boot; `rpi-rgb-led-matrix` Python bindings built (after adding
  `python3-pil` for `Imaging.h`) and `MatrixDisplay` initialises without
  falling back to the terminal, i.e. the driver is talking to the HAT.
- Not yet verified: the physical panel lighting up correctly (wiring,
  `--slowdown`, colour order).

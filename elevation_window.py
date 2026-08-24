#!/usr/bin/env python3
"""
Elevation window: drift a 32x16 window slowly across the world and show the
elevation of the captured rectangle on an RGB LED matrix.

Elevation comes straight from the local ETOPO1 GeoTIFF (no server needed).
If the rgbmatrix library isn't installed (i.e. you're on a laptop, not the Pi)
the frame is drawn in the terminal instead.

A small built-in web page (http://<pi>/ , or http://localhost:8080/ on a
laptop) mirrors the panel live and shows where on a world map the window is,
with a trail of where it has been.

Run on the Pi:
    sudo python3 elevation_window.py --slowdown 2

Try it on a laptop:
    python3 elevation_window.py --interval 0.2 --web-port 8080
"""

import argparse
import json
import math
import os
import random
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import rasterio
from rasterio.enums import Resampling

######## Setup Section #############
COLS = 32
ROWS = 16

# degrees of latitude covered by one pixel; longitude spacing is stretched by
# 1/cos(lat) so pixels stay roughly square on the ground.
DEG_PER_PIXEL = 0.1

# how far the window drifts each tick, in degrees, and how often
STEP_DEG = 0.005
INTERVAL_S = 1.0

# slightly randomize the heading when the window bounces off the poles
BOUNCE_JITTER = 0.2

# below this many metres of relief in a frame, stop stretching the colours
# (avoids a flat frame turning into rainbow noise, or a divide by zero)
MIN_SPAN_M = 300

# nudge brightness down when driving the panel; 255 everywhere is blinding
MAX_BRIGHTNESS = 200

# hardware brightness of the LED panel, 1-100. Dims via PWM so colours keep
# their full resolution; does not affect the web page.
PANEL_BRIGHTNESS = 70

# land colour scheme:
#   "map"  - hypsometric tints like a paper map: green lowlands, yellow/amber
#            middle ground, orange-brown high ground, white peaks
#   "fire" - the original: dim red -> red -> yellow
PALETTE = "map"

# colour stops for the "map" palette as (fraction of frame relief, (r, g, b))
MAP_STOPS = [
    (0.00, (15, 110, 25)),     # lowland green (deep, low red/blue = richer)
    (0.25, (120, 170, 40)),    # yellow-green
    (0.45, (220, 190, 70)),    # tan / yellow
    (0.65, (200, 120, 40)),    # amber-brown
    (0.85, (170, 90, 60)),     # brown
    (1.00, (255, 255, 255)),   # snowy peaks
]

# physical panel orientation: flip so north is at the top. Only affects the
# LED panel; the web page is always drawn north-up.
PANEL_FLIP_VERTICAL = True
PANEL_FLIP_HORIZONTAL = True

# world map served to the web page: size in cells, and a cache so the Pi
# doesn't re-read the whole 466 MB GeoTIFF on every boot
MAP_W, MAP_H = 360, 180
MAP_CACHE = "world_map_cache.npy"

# how many past positions the web page's trail keeps
TRAIL_LEN = 2000

DEFAULT_TIF = "opentopodata/data/etopo1/ETOPO1.tif"


######### Elevation from the raster #########

class ElevationRaster:
    def __init__(self, path):
        self.ds = rasterio.open(path)
        self.transform = self.ds.transform
        self.width = self.ds.width
        self.height = self.ds.height

    def close(self):
        self.ds.close()

    @staticmethod
    def lon_step(center_lat):
        return DEG_PER_PIXEL / max(math.cos(math.radians(center_lat)), 0.05)

    def sample_window(self, center_lat, center_lon):
        """Return a ROWS x COLS array of elevations (metres) centred on the point."""
        lat_step = DEG_PER_PIXEL
        lon_step = self.lon_step(center_lat)

        # row 0 is the top (north) of the panel
        lats = center_lat + (ROWS / 2 - 0.5 - np.arange(ROWS)) * lat_step
        lons = center_lon + (np.arange(COLS) - COLS / 2 + 0.5) * lon_step
        lons = (lons + 180.0) % 360.0 - 180.0   # wrap across the date line

        rows, cols = rasterio.transform.rowcol(self.transform, lons.tolist(), [center_lat] * COLS)
        rows_lat, _ = rasterio.transform.rowcol(self.transform, [center_lon] * ROWS, lats.tolist())
        rows_lat = np.clip(np.array(rows_lat), 0, self.height - 1)
        cols = np.array(cols) % self.width

        rmin, rmax = int(rows_lat.min()), int(rows_lat.max())
        block = self.ds.read(1, window=((rmin, rmax + 1), (0, self.width)))
        return block[rows_lat - rmin][:, cols].astype(np.int32)

    def world_map(self, cache_path=MAP_CACHE):
        """Return a MAP_H x MAP_W elevation array of the whole world (cached)."""
        if os.path.exists(cache_path):
            m = np.load(cache_path)
            if m.shape == (MAP_H, MAP_W):
                return m
        print("building world map from the GeoTIFF (one-off, can take a minute on a Pi)...")
        m = self.ds.read(1, out_shape=(MAP_H, MAP_W), resampling=Resampling.average).astype(np.int32)
        try:
            np.save(cache_path, m)
        except OSError as e:
            print(f"could not cache world map: {e}")
        return m


######### Elevation -> colour #########

def _interp_stops(t, stops):
    """Piecewise-linear colour ramp: t in 0..1 (array) -> (..., 3) floats."""
    xs = np.array([x for x, _ in stops])
    cols = np.array([c for _, c in stops], dtype=float)
    out = np.empty(t.shape + (3,))
    for ch in range(3):
        out[..., ch] = np.interp(t, xs, cols[:, ch])
    return out


def elevation_to_rgb(elev, brightness=MAX_BRIGHTNESS):
    """
    Map an elevation array to an (..., 3) uint8 array.
    Sea level is a fixed anchor; the scale above/below it adapts to the frame.
      below 0 : deep blue -> bright blue as it shallows
      above 0 : depends on PALETTE (see top of file)
    """
    rgb = np.zeros(elev.shape + (3,), dtype=np.uint8)
    land = elev > 0
    sea = ~land

    if sea.any():
        depth = -elev[sea].astype(float)
        span = max(depth.max(), MIN_SPAN_M)
        b = 255 - (depth / span) * 200          # shallow = 255, deepest = 55
        rgb[sea, 2] = b.astype(np.uint8)

    if land.any():
        h = elev[land].astype(float)
        span = max(h.max(), MIN_SPAN_M)
        t = h / span                            # 0..1 across the frame's relief
        if PALETTE == "map":
            rgb[land] = _interp_stops(t, MAP_STOPS).astype(np.uint8)
        else:
            r = 60 + np.minimum(t * 2, 1.0) * 195   # first half: red climbs
            g = np.clip((t - 0.5) * 2, 0, 1) * 255  # second half: green spills in
            rgb[land, 0] = r.astype(np.uint8)
            rgb[land, 1] = g.astype(np.uint8)

    return (rgb.astype(np.uint16) * brightness // 255).astype(np.uint8)


def rgb_to_hex_rows(rgb):
    """(H, W, 3) uint8 -> list of H strings, each W*6 hex chars."""
    return [bytes(row.reshape(-1)).hex() for row in rgb]


######### Output: real matrix or terminal #########

class MatrixDisplay:
    def __init__(self, slowdown, mapping):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        opts = RGBMatrixOptions()
        opts.rows = ROWS
        opts.cols = COLS
        opts.hardware_mapping = mapping
        opts.gpio_slowdown = slowdown
        opts.brightness = PANEL_BRIGHTNESS
        opts.drop_privileges = False
        self.matrix = RGBMatrix(options=opts)
        self.canvas = self.matrix.CreateFrameCanvas()

    def show(self, rgb):
        if PANEL_FLIP_VERTICAL:
            rgb = rgb[::-1]
        if PANEL_FLIP_HORIZONTAL:
            rgb = rgb[:, ::-1]
        for y in range(ROWS):
            for x in range(COLS):
                r, g, b = rgb[y, x]
                self.canvas.SetPixel(x, y, int(r), int(g), int(b))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)


class TerminalDisplay:
    def show(self, rgb):
        lines = []
        for y in range(ROWS):
            line = ""
            for x in range(COLS):
                r, g, b = rgb[y, x]
                line += f"\033[48;2;{r};{g};{b}m  "
            lines.append(line + "\033[0m")
        print("\033[H\033[J" + "\n".join(lines))


######### Web page #########

class SharedState:
    """What the web server is allowed to see. Written by the main loop only."""
    def __init__(self, interval):
        self.lock = threading.Lock()
        self.interval = interval
        self.lat = self.lon = self.heading = 0.0
        self.frame_hex = []
        self.elev_min = self.elev_max = 0
        self.trail = deque(maxlen=TRAIL_LEN)
        self.map_json = b"{}"

    def update(self, lat, lon, heading, elev, rgb):
        with self.lock:
            self.lat, self.lon, self.heading = lat, lon, heading
            self.frame_hex = rgb_to_hex_rows(rgb)
            self.elev_min, self.elev_max = int(elev.min()), int(elev.max())
            self.trail.append((round(lat, 3), round(lon, 3)))

    def state_json(self):
        with self.lock:
            d = {
                "lat": round(self.lat, 4),
                "lon": round(self.lon, 4),
                "heading": round(math.degrees(self.heading) % 360, 1),
                "interval": self.interval,
                "cols": COLS, "rows": ROWS,
                "half_h": ROWS / 2 * DEG_PER_PIXEL,
                "half_w": COLS / 2 * ElevationRaster.lon_step(self.lat),
                "elev_min": self.elev_min, "elev_max": self.elev_max,
                "frame": self.frame_hex,
                "trail": list(self.trail),
            }
        return json.dumps(d).encode()


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>elevation window</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{margin:0;background:#0b0b10;color:#bbb;font:14px/1.4 system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;gap:18px;padding:18px}
 canvas{max-width:100%;height:auto;image-rendering:pixelated;border-radius:6px}
 #grid{background:#000}
 .info{display:flex;gap:24px;flex-wrap:wrap;justify-content:center;color:#888}
 .info b{color:#ddd;font-variant-numeric:tabular-nums}
 h1{font-size:15px;font-weight:500;letter-spacing:.08em;color:#777;margin:0;text-transform:uppercase}
</style></head><body>
<h1>elevation window</h1>
<canvas id="grid" width="640" height="320"></canvas>
<div class="info">
 <span>centre <b id="pos">–</b></span>
 <span>heading <b id="hdg">–</b></span>
 <span>elevation <b id="elev">–</b></span>
</div>
<canvas id="map" width="1080" height="540"></canvas>
<script>
const grid=document.getElementById('grid'),gctx=grid.getContext('2d');
const map=document.getElementById('map'),mctx=map.getContext('2d');
let mapImg=null;

function drawGrid(s){
  const cw=grid.width/s.cols,ch=grid.height/s.rows;
  gctx.fillStyle='#000';gctx.fillRect(0,0,grid.width,grid.height);
  for(let y=0;y<s.rows;y++){const row=s.frame[y];
    for(let x=0;x<s.cols;x++){
      gctx.fillStyle='#'+row.substr(x*6,6);
      gctx.beginPath();gctx.arc(x*cw+cw/2,y*ch+ch/2,cw*0.38,0,6.283);gctx.fill();
    }}
}
function toXY(lat,lon){return [(lon+180)/360*map.width,(90-lat)/180*map.height];}
function drawMap(s){
  if(mapImg)mctx.drawImage(mapImg,0,0,map.width,map.height);
  else{mctx.fillStyle='#111';mctx.fillRect(0,0,map.width,map.height);}
  // trail, broken where it wraps the date line
  mctx.strokeStyle='rgba(255,255,255,0.55)';mctx.lineWidth=1.5;mctx.beginPath();
  let prev=null;
  for(const [la,lo] of s.trail){const [x,y]=toXY(la,lo);
    if(prev&&Math.abs(lo-prev)<180)mctx.lineTo(x,y);else mctx.moveTo(x,y);prev=lo;}
  mctx.stroke();
  // the window
  const [x0,y0]=toXY(s.lat+s.half_h,s.lon-s.half_w),[x1,y1]=toXY(s.lat-s.half_h,s.lon+s.half_w);
  mctx.strokeStyle='#fff';mctx.lineWidth=2;
  mctx.strokeRect(x0-2,y0-2,Math.max(x1-x0,3)+4,Math.max(y1-y0,3)+4);
}
async function loadMap(){
  const m=await (await fetch('map.json')).json();
  const c=document.createElement('canvas');c.width=m.w;c.height=m.h;
  const ctx=c.getContext('2d'),img=ctx.createImageData(m.w,m.h);
  for(let y=0;y<m.h;y++){const row=m.rows[y];
    for(let x=0;x<m.w;x++){const i=(y*m.w+x)*4,p=x*6;
      img.data[i]=parseInt(row.substr(p,2),16);img.data[i+1]=parseInt(row.substr(p+2,2),16);
      img.data[i+2]=parseInt(row.substr(p+4,2),16);img.data[i+3]=255;}}
  ctx.putImageData(img,0,0);mapImg=c;
}
async function tick(){
  let wait=1000;
  try{const s=await (await fetch('state.json',{cache:'no-store'})).json();
    wait=Math.max(250,s.interval*1000);
    drawGrid(s);drawMap(s);
    pos.textContent=s.lat.toFixed(3)+', '+s.lon.toFixed(3);
    hdg.textContent=s.heading.toFixed(0)+'°';
    elev.textContent=s.elev_min+' to '+s.elev_max+' m';
  }catch(e){}
  setTimeout(tick,wait);
}
loadMap().then(tick,tick);
</script></body></html>
"""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", PAGE.encode())
            elif self.path.startswith("/state.json"):
                self._send(200, "application/json", state.state_json(), nocache=True)
            elif self.path.startswith("/map.json"):
                self._send(200, "application/json", state.map_json)
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code, ctype, body, nocache=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if nocache:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass   # keep the panel's log clean

    return Handler


def start_web(state, port):
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"web page on port {port}")
    return server


######### The drifting window #########

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tif", default=DEFAULT_TIF, help="path to ETOPO1.tif")
    ap.add_argument("--start", default="40.7,-74.0", help="starting centre as lat,lon")
    ap.add_argument("--heading", type=float, default=30.0, help="initial heading in degrees (0=north, 90=east)")
    ap.add_argument("--interval", type=float, default=INTERVAL_S, help="seconds between frames")
    ap.add_argument("--slowdown", type=int, default=1, help="rgbmatrix gpio_slowdown (0-1 for Pi 1/Zero, 2-4 for Pi 3/4)")
    ap.add_argument("--mapping", default="adafruit-hat", help="rgbmatrix hardware_mapping: adafruit-hat, or adafruit-hat-pwm if the GPIO4-GPIO18 jumper is soldered")
    ap.add_argument("--terminal", action="store_true", help="force terminal output even if rgbmatrix is installed")
    ap.add_argument("--web-port", type=int, default=80, help="port for the live web page (80 needs root)")
    ap.add_argument("--no-web", action="store_true", help="don't run the web page")
    args = ap.parse_args()

    lat, lon = (float(v) for v in args.start.split(","))
    heading = math.radians(args.heading)
    lat_limit = 90.0 - (ROWS / 2) * DEG_PER_PIXEL

    display = None
    if not args.terminal:
        try:
            display = MatrixDisplay(args.slowdown, args.mapping)
        except ImportError:
            print("rgbmatrix not available, drawing to terminal")
    if display is None:
        display = TerminalDisplay()

    raster = ElevationRaster(args.tif)
    state = SharedState(args.interval)
    if not args.no_web:
        world = raster.world_map()
        state.map_json = json.dumps({
            "w": MAP_W, "h": MAP_H,
            "rows": rgb_to_hex_rows(elevation_to_rgb(world, brightness=255)),
        }).encode()
        try:
            start_web(state, args.web_port)
        except PermissionError:
            print(f"port {args.web_port} needs root; use --web-port 8080 or run with sudo. continuing without web page")

    try:
        while True:
            elev = raster.sample_window(lat, lon)
            rgb = elevation_to_rgb(elev)
            display.show(rgb)
            state.update(lat, lon, heading, elev, rgb)
            print(f"centre {lat:8.3f}, {lon:9.3f}   min {elev.min():6d} m   max {elev.max():6d} m")

            lat += STEP_DEG * math.cos(heading)
            lon += STEP_DEG * math.sin(heading)
            lon = (lon + 180.0) % 360.0 - 180.0

            # bounce off the poles, jittering the heading so the path doesn't repeat
            if lat > lat_limit or lat < -lat_limit:
                lat = max(-lat_limit, min(lat_limit, lat))
                heading = math.pi - heading + random.uniform(-BOUNCE_JITTER, BOUNCE_JITTER)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        raster.close()


if __name__ == "__main__":
    main()

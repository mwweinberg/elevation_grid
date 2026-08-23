# Setting up the elevation window on a Raspberry Pi

Start-to-finish instructions: blank SD card to a panel that starts on boot.
Written for a Pi 3 Model B (v1.2) running Raspberry Pi OS Lite 32-bit
(Trixie, Aug 2026) with the Adafruit RGB Matrix + RTC HAT
(product 3920) and a 16x32 HUB75 panel, developed from a Linux laptop over
SSH. Notes for other boards are marked.

Rough time: 30-45 minutes, most of it waiting for `apt` and the matrix
library to compile.

Placeholders used below:

- `elevationgrid` – the hostname you give the Pi (so it's `elevationgrid.local`)
- `pi` – the username you give the Pi
- `~/Documents/programming/python/elevation_grid` – this project on the laptop

---

## 0. Hardware checklist

- Pi 3 Model B (or B+, Pi 4, Zero 2 W, Zero W, B+/2 — anything with a 40-pin
  header that is **not** a Pi 5)
- Adafruit RGB Matrix + RTC HAT, seated on all 40 pins
- 16x32 HUB75 panel, ribbon cable from the HAT's IDC socket to the panel's
  **input** connector (usually marked with an arrow pointing away from it)
- Panel power: the HAT's screw terminals to the panel's power leads,
  **red to +5V, black to GND**. Double-check polarity; reversed power kills
  panels.
- 5 V power supply, 2 A minimum, into the HAT's 2.1 mm DC jack. This powers
  the panel *and* the Pi through the HAT — you do **not** also plug in the
  Pi's micro-USB. (A 16x32 panel draws about 2 A worst case at full white;
  the script's `MAX_BRIGHTNESS` keeps it well under that.)
- Optional: CR1220 coin cell in the HAT's RTC holder.
- microSD card, 8 GB or larger (the elevation file alone is 466 MB).
- Optional but recommended for the "quality" install mode in step 5:
  a blob of solder bridging the HAT's **GPIO4 to GPIO18** jumper pads. Skip
  this if you don't want to solder; the panel will still work.

---

## 1. Write the OS to the SD card

Install Raspberry Pi Imager on the laptop (`sudo apt install rpi-imager`, or
from https://www.raspberrypi.com/software/). Then:

1. Choose device: **Raspberry Pi 3**.
2. Choose OS: **Raspberry Pi OS (other) → Raspberry Pi OS Lite (32-bit)**.
   - *Lite* because there's no need for a desktop.
   - *32-bit* deliberately: it runs on every Pi from the original to the 4,
     so this SD card can be moved to a Zero / Zero 2 W later unchanged.
3. Choose storage: the SD card.
4. Click **Next**, then **Edit Settings** for the OS customisation:
   - General: hostname `elevationgrid` (this is what makes
     `http://elevationgrid.local/` work later); username `pi` and a password;
     your Wi-Fi SSID/password and country; your locale/timezone.
   - Services: **Enable SSH**, "Use password authentication" (or paste your
     public key — `cat ~/.ssh/id_ed25519.pub` — for passwordless login).
   - Save, then **Yes** to apply, **Yes** to write.
5. When it finishes, put the card in the Pi.

Command-line alternative if you prefer: `rpi-imager --cli` exists but doesn't
do the customisation step; the GUI is genuinely the more convenient tool here.

---

## 2. First boot and SSH

Plug the HAT's power supply in. First boot takes a minute or two (it resizes
the filesystem and reboots once). Then, from the laptop:

    ssh pi@elevationgrid.local

If `.local` doesn't resolve, find the IP from your router, or
`ping elevationgrid.local` after a minute, or `nmap -sn 192.168.1.0/24`
(adjust for your subnet).

Once in, update everything (this can take 5-10 minutes on a Pi 3):

    sudo apt update && sudo apt full-upgrade -y
    sudo reboot

Reconnect after the reboot.

If you want to script the rest from the laptop (or let an assistant do it),
note that Trixie no longer gives the `pi` user passwordless sudo. Restore it
with:

    echo "pi ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_pi-nopasswd

and copy your SSH key over with `ssh-copy-id pi@elevationgrid.local` from the
laptop. Remove the sudoers file afterwards if you'd rather not leave it.

### Automatic updates

    sudo apt install -y unattended-upgrades apt-listchanges

The package's default origin list only matches Debian security updates,
which never apply to a Pi, so tell it about the Raspberry Pi repos and let it
reboot at a quiet hour when a kernel update needs it:

    sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'EOF'
    APT::Periodic::Update-Package-Lists "1";
    APT::Periodic::Download-Upgradeable-Packages "1";
    APT::Periodic::Unattended-Upgrade "1";
    APT::Periodic::AutocleanInterval "7";
    EOF
    sudo tee /etc/apt/apt.conf.d/52unattended-upgrades-local >/dev/null <<'EOF'
    Unattended-Upgrade::Origins-Pattern {
            "origin=Raspbian,codename=${distro_codename}";
            "origin=Raspberry Pi Foundation,codename=${distro_codename}";
            "origin=Debian,codename=${distro_codename},label=Debian-Security";
    };
    Unattended-Upgrade::Remove-Unused-Dependencies "true";
    Unattended-Upgrade::Automatic-Reboot "true";
    Unattended-Upgrade::Automatic-Reboot-Time "04:30";
    EOF
    sudo systemctl enable --now unattended-upgrades
    sudo unattended-upgrade --dry-run -d 2>&1 | grep "Allowed origins"

The service (step 7) restarts automatically after the reboot.

---

## 3. Install the Python raster libraries

    sudo apt install -y python3-rasterio python3-numpy

Use `apt`, not `pip`: these are prebuilt for the Pi. `pip install rasterio`
would try to compile GDAL, which is slow on a Pi 3 and worse on ARMv6 boards.

Sanity check:

    python3 -c "import rasterio, numpy; print(rasterio.__version__, numpy.__version__)"

---

## 4. Copy the project to the Pi

From the **laptop**:

    cd ~/Documents/programming/python/elevation_grid
    ssh pi@elevationgrid.local mkdir -p elevation_grid
    rsync -avP elevation_window.py readme.md DESIGN.md pi_install_instructions.md \
        pi@elevationgrid.local:elevation_grid/
    rsync -avP --relative opentopodata/data/etopo1/ETOPO1.tif \
        pi@elevationgrid.local:elevation_grid/

The second `rsync` copies the 466 MB elevation file into the same relative
path (`elevation_grid/opentopodata/data/etopo1/ETOPO1.tif`), which is where
the script looks by default. Over Wi-Fi expect a few minutes.

Now, on the **Pi**, prove the raster half works before touching the panel:

    cd ~/elevation_grid
    python3 elevation_window.py --terminal --interval 0.5 --start 27.9,86.9 --web-port 8080

The first run prints `building world map from the GeoTIFF...` and takes up to
a minute while it reads the whole file once (it caches the result in
`world_map_cache.npy`; later starts are instant). Then you should see a
coloured 32x16 block redrawing in the terminal (Everest region: red/yellow
land) and a `centre ... min ... max` line each frame.

While it's running, open **http://elevationgrid.local:8080/** in a browser on
the laptop or your phone: the same frame as big dots, plus a world map with
the window's position and trail. (Port 8080 here because we're not root yet;
the final service uses port 80 so the address is just
`http://elevationgrid.local/`.)

Ctrl-C to stop. If this fails, fix it now — everything after this only adds
the panel.

---

## 5. Install the matrix driver (`rpi-rgb-led-matrix`)

Two routes. **Route A** is Adafruit's installer script written for exactly
this HAT; it does everything in Route B for you. Use A unless it breaks.

### Route A: Adafruit installer

    cd ~
    curl -O https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh
    sudo bash rgb-matrix.sh

It asks:

- **Interface board type** → `1` (Adafruit RGB Matrix HAT + RTC).
- **Install RTC support?** → `y` (harmless even if you never use it).
- **Quality or convenience?**
  - `1` **Quality** — if you soldered the GPIO4-GPIO18 jumper. Disables
    onboard audio, gives steadier PWM. Use `--mapping adafruit-hat-pwm`
    when running the script later.
  - `2` **Convenience** — no soldering. Slight flicker possible; audio still
    works. Use the script's default `--mapping adafruit-hat`.
- Confirm, then wait 10-15 minutes while it compiles the library and Python
  bindings. Reboot when it says to:

      sudo reboot

### Route B: manual (if Route A fails, or you like knowing what happened)

This is what was actually done on the Trixie install. The Python bindings are
now a normal `pip` package; they need Pillow's C headers to build, which on
Raspberry Pi OS come from `python3-pil`.

    sudo apt install -y git build-essential python3-dev python3-pip python3-pil cython3
    cd ~
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make -j4 -C examples-api-use
    sudo pip install . --break-system-packages

`--break-system-packages` is needed because the script runs with the system
Python as root; it only installs this one self-contained package. The build
takes several minutes on a Pi 3. If it fails with `Imaging.h: No such file`,
`python3-pil` is missing.

Then disable onboard audio, which shares hardware with the panel's PWM
timing:

    echo "dtparam=audio=off" | sudo tee -a /boot/firmware/config.txt
    echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
    sudo update-initramfs -u

(On older Bullseye images the file is `/boot/config.txt`.)

Recommended on any multi-core Pi (Pi 2/3/4/Zero 2): reserve a CPU core for
the panel refresh so nothing else can cause flicker. Append ` isolcpus=3` to
the single line in `/boot/firmware/cmdline.txt` (keep it all on one line):

    sudo sed -i 's/$/ isolcpus=3/' /boot/firmware/cmdline.txt

Then `sudo reboot`.

### Verify the driver with hzeller's demo (both routes)

The Adafruit script clones the library into `~/rpi-rgb-led-matrix` too, so
this works either way:

    cd ~/rpi-rgb-led-matrix/examples-api-use
    sudo ./demo -D0 --led-rows=16 --led-cols=32 --led-gpio-mapping=adafruit-hat --led-slowdown-gpio=2

(`--led-gpio-mapping=adafruit-hat-pwm` if you chose Quality.) You should see
a rotating square. Ctrl-C to stop. If it's flickery or garbled, try
`--led-slowdown-gpio=1` or `3`. Note the value that looks best — that's your
`--slowdown`.

Also confirm the Python binding is visible **to root**, which is how the
script runs:

    sudo python3 -c "import rgbmatrix; print('ok')"

---

## 6. Run the elevation window on the panel

    cd ~/elevation_grid
    sudo python3 elevation_window.py --slowdown 2

Add `--mapping adafruit-hat-pwm` if you chose Quality mode. Useful options:

    --start 27.9,86.9      # start over the Himalayas
    --start 0,-179.9       # start on the date line (tests wrap-around)
    --interval 0.2         # drift faster
    --heading 90           # drift due east

`sudo` is required: the driver needs raw GPIO access. Ctrl-C stops it and
blanks the panel. Because it's running as root the web page is now on the
normal port: **http://elevationgrid.local/**.

Look at it for a while and adjust the constants at the top of
`elevation_window.py` (`DEG_PER_PIXEL`, `STEP_DEG`, `MAX_BRIGHTNESS`,
colours in `elevation_to_rgb`) — see `readme.md` for what each does. Edit on
the Pi with `nano`, or edit on the laptop and re-run the first `rsync` from
step 4.

---

## 7. Start on boot (systemd)

    sudo tee /etc/systemd/system/elevation-window.service >/dev/null <<'UNIT'
    [Unit]
    Description=Elevation window LED matrix
    After=local-fs.target

    [Service]
    Type=simple
    WorkingDirectory=/home/pi/elevation_grid
    ExecStart=/usr/bin/python3 /home/pi/elevation_grid/elevation_window.py --slowdown 2
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    UNIT

    sudo systemctl daemon-reload
    sudo systemctl enable --now elevation-window

(Add `--mapping adafruit-hat-pwm` to `ExecStart` if applicable. Change the
username paths if yours isn't `pi`.)

Day-to-day commands:

    sudo systemctl status elevation-window       # is it running?
    sudo journalctl -u elevation-window -f       # live log (the "centre ..." lines)
    sudo systemctl stop elevation-window         # stop it (e.g. to run by hand)
    sudo systemctl restart elevation-window      # after editing the script

Remember to **stop the service before running the script manually** — two
processes fighting over the panel produces garbage.

---

## 8. Optional: use the HAT's real-time clock

Only matters if you ever want correct time without a network. Put a CR1220
in the holder, then (Route A already did the first line if you said `y`):

    echo "dtoverlay=i2c-rtc,ds1307" | sudo tee -a /boot/firmware/config.txt
    sudo apt install -y i2c-tools
    sudo reboot
    sudo hwclock -w        # write the current (NTP-synced) time to the RTC
    sudo hwclock -r        # read it back

---

## 9. Moving to a different Pi later

- **Zero 2 W**: pull the SD card out of the Pi 3, put it in the Zero 2 W.
  Everything works unchanged, same `--slowdown`. The HAT overhangs the board
  but works.
- **Zero / Zero W (single-core ARMv6)**: same SD card also boots. Change
  `--slowdown 2` to `0` or `1`, remove `isolcpus=3` from `cmdline.txt` (there
  is no core 3), and raise `--interval` if you see flicker.
- **Original 26-pin Model B**: does not work — the HAT needs the 40-pin
  header (see `DESIGN.md`).
- **Pi 5**: does not work with this driver at all.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Panel dark, no errors | Ribbon in the panel's *output* socket instead of input; panel power not connected; check screw terminals. |
| Panel shows garbage / random flicker | Wrong `--slowdown` (try 1, 2, 3); or something else using GPIO. Try the hzeller demo to separate hardware from software. |
| Faint flicker under load | Add `isolcpus=3` (step 5); use Quality mode with the jumper; raise `--interval`. |
| `ModuleNotFoundError: rgbmatrix` when run with sudo | Bindings installed for a different Python (e.g. into a venv). Re-run `sudo pip install . --break-system-packages` in `~/rpi-rgb-led-matrix`. |
| Build fails: `Imaging.h: No such file or directory` | `sudo apt install python3-pil` and rebuild. |
| `ModuleNotFoundError: rasterio` | Step 3 skipped, or you're inside a venv. Use system `python3`. |
| `RasterioIOError: ... ETOPO1.tif: No such file` | The second `rsync` in step 4 didn't land at `elevation_grid/opentopodata/data/etopo1/ETOPO1.tif`; or pass `--tif /path/to/ETOPO1.tif`. |
| "Can't set realtime thread priority" / snd_bcm2835 warning | Audio not disabled. Redo the audio lines in Route B and reboot. |
| Colours wrong (e.g. sea is red) | Panel has an unusual RGB order: add `opts.led_rgb_sequence = "RBG"` (or similar) in `MatrixDisplay.__init__`. |
| Pi reboots / browns out when panel lights up | Power supply too weak; use 5 V ≥ 2.5 A, and lower `MAX_BRIGHTNESS`. |
| Service starts before the panel and shows nothing | Rare; add `ExecStartPre=/bin/sleep 5` to the unit. |
| `http://elevationgrid.local/` doesn't load | Check `sudo systemctl status elevation-window` is running; try the IP address instead (`hostname -I` on the Pi) — if that works it's mDNS: make sure your computer/phone is on the same Wi-Fi, and on Windows that Bonjour/mDNS is available. `port 80 needs root` in the log means it was started without sudo. |
| Web page shows the grid but a blank/dark map | `map.json` failed; check the log for `could not cache world map` (directory not writable — harmless, it rebuilds each start) or a rasterio error. |

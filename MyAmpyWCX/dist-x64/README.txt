MyAmpy WFX x64

Files:
- MyAmpy.wfx64
- plugin.ini

Install in Total Commander x64:
1. Open Configuration -> Options -> Plugins.
2. In "File system plugins (.WFX)" choose "Add".
3. Select MyAmpy.wfx64.
4. Confirm plugin installation.

Configuration:
- Edit plugin.ini next to the plugin file.
- Default values:
  Port=COM3
  Baud=115200
  AmpyPath=ampy.exe
- If Total Commander cannot find ampy from PATH, set:
  AmpyPath=C:\dev\python\Scripts\ampy.exe

Requirements:
- Total Commander x64
- Python with adafruit-ampy installed:
  pip install adafruit-ampy
- ampy must be available in PATH

Notes:
- This plugin uses ampy to talk to the MicroPython device.
- If the device is on another COM port, update plugin.ini.
- plugin.ini is loaded from the plugin directory.

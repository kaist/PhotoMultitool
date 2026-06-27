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

Requirements:
- Total Commander x64
- A MicroPython device available on the configured COM port

Notes:
- This plugin talks directly to the MicroPython raw REPL over serial.
- If the device is on another COM port, update plugin.ini.
- plugin.ini is loaded from the plugin directory.

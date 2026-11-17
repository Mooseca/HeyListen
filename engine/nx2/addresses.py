"""The addresses HeyListen's tools send to, from nx2/addresses.ini: kept out of the code, to edit in one place.

    address("telemetry")   -> the telemetry server's https address, or "" when it isn't set (nothing is then sent)
"""
import configparser
import os

ADDRESSES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addresses.ini")


def address(key, path=ADDRESSES):
    """A service's address; "" when it isn't there. A BOM (utf-8-sig) is fine, and a file that doesn't parse turns the
    uses off: it never stops the builders"""
    ini = configparser.ConfigParser(interpolation=None)
    try:
        ini.read(path, encoding="utf-8-sig")
        return ini.get("addresses", key, fallback="").strip()
    except (configparser.Error, UnicodeDecodeError):
        return ""


def stamp_lines(path=ADDRESSES):
    """The lines make_game.py writes into hookshot_version.txt: telemetry= (only an https:// address on one line, else
    nothing) and crash_issue= (likewise)."""
    out = []
    for key in ("telemetry", "crash_issue"):
        value = address(key, path)
        if value.startswith("https://") and " " not in value and "\n" not in value:
            out.append("%s=%s\n" % (key, value.rstrip("/") if key == "telemetry" else value))
    return out

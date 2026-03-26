import uos
import utime

_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
_LEVEL_NAMES = {0: "DBG", 1: "INF", 2: "WRN", 3: "ERR"}
_LEVEL_COLORS = {
    0: "\033[36m",   # Cyan für DEBUG
    1: "\033[32m",   # Grün für INFO
    2: "\033[33m",   # Gelb für WARNING
    3: "\033[31m",   # Rot für ERROR
}
_RESET = "\033[0m"
_DIM = "\033[2m"

class Logger:
    def __init__(self, filename="scansync.log", level="INFO", max_bytes=32768):
        self._filename = filename
        self._level = _LEVELS.get(level.upper(), 1)
        self._max_bytes = max_bytes

    def _rotate(self):
        try:
            stat = uos.stat(self._filename)
            if stat[6] >= self._max_bytes:
                backup = self._filename + ".old"
                try:
                    uos.remove(backup)
                except OSError:
                    pass
                uos.rename(self._filename, backup)
        except OSError:
            pass

    def _log(self, level_num, msg):
        if level_num < self._level:
            return
        self._rotate()
        tag = _LEVEL_NAMES.get(level_num, "???")
        color = _LEVEL_COLORS.get(level_num, "")
        t = utime.localtime()
        ts = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])
        line = "[{}] {} {}".format(ts, tag, msg)
        print("{}{}{} {}{}{} {}".format(_DIM, ts, _RESET, color, tag, _RESET, msg))
        try:
            with open(self._filename, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def debug(self, msg):
        self._log(0, msg)

    def info(self, msg):
        self._log(1, msg)

    def warning(self, msg):
        self._log(2, msg)

    def error(self, msg):
        self._log(3, msg)

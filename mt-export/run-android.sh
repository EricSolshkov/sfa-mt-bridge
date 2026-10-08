#!/system/bin/sh
# This launcher only runs the Python exporter. It never invokes sing-box or su.
set -eu
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${MT_EXPORT_PYTHON:-}" ]; then
    PYTHON_BIN=$MT_EXPORT_PYTHON
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python)
elif [ -x /data/data/com.termux/files/usr/bin/python ]; then
    PYTHON_BIN=/data/data/com.termux/files/usr/bin/python
else
    echo 'Python not found. Install Python in Termux, or set MT_EXPORT_PYTHON.' >&2
    exit 1
fi
exec "$PYTHON_BIN" -X utf8 "$SCRIPT_DIR/update_mt.py" "$@"

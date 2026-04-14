"""Daonna desktop launcher — runs Flask inside a pywebview native window."""

import logging
import socket
import sys
import threading
from contextlib import closing

import webview

from server import app as flask_app


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_flask(port: int) -> None:
    # Silence Werkzeug's request log so the console stays clean in desktop mode.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    flask_app.run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main() -> None:
    port = _find_free_port()
    server_thread = threading.Thread(target=_run_flask, args=(port,), daemon=True)
    server_thread.start()

    window = webview.create_window(
        title="Daonna",
        url=f"http://127.0.0.1:{port}",
        width=440,
        height=700,
        min_size=(380, 560),
        background_color="#0f1115",
        text_select=True,
        confirm_close=False,
    )

    # Start the native event loop. Blocks until the window closes.
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()

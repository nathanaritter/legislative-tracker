"""
app.py — Legislative Tracker entry point.
"""

import logging

from dash import Dash
import dash_bootstrap_components as dbc

from config import BASE_DIR
from components.layout import build_layout

logger = logging.getLogger(__name__)

app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
    ],
    assets_folder=str(BASE_DIR / "assets"),
    title="Legislative Tracker",
    suppress_callback_exceptions=True,
    update_title=None,
)

# Use the Lucide "gavel" icon (MIT-licensed, pre-designed by the Lucide team)
# as the favicon. The SVG is scaled crisply by the browser at any size. A
# small PNG fallback covers the handful of legacy browsers without SVG
# favicon support. Cache-bust via version query string so the user sees the
# new file immediately after upgrades.
app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg?v=2">
        <link rel="alternate icon" href="/assets/favicon.png?v=2">
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

server = app.server
app.layout = build_layout()

# Self-registering callback modules
from callbacks import filters        # noqa: E402,F401
from callbacks import timeline       # noqa: E402,F401
from callbacks import detail         # noqa: E402,F401
from callbacks import state_io       # noqa: E402,F401
from callbacks import navbar         # noqa: E402,F401


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8060))
    logger.info("Starting Legislative Tracker at http://localhost:%s", port)
    app.run(debug=False, host="0.0.0.0", port=port)

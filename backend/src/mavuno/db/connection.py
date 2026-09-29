from __future__ import annotations

import ssl
from typing import Any

from sqlalchemy.engine import make_url


def database_connection_options(database_url: str) -> tuple[str, dict[str, Any]]:
    """Convert a MySQL CA URL option into the SSLContext expected by aiomysql."""
    url = make_url(database_url)
    ca_file = url.query.get("ssl_ca")
    if ca_file is None:
        return database_url, {}
    if not isinstance(ca_file, str):
        raise ValueError("The database SSL CA path must be a single file")

    context = ssl.create_default_context(cafile=ca_file)
    safe_url = url.difference_update_query(["ssl_ca"])
    return safe_url.render_as_string(hide_password=False), {"ssl": context}

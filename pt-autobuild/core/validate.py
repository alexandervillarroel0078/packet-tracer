"""
core.validate - validaciones de FORMATO de la entrada (no de alcanzabilidad).

    valid_ipish(s)    -> bool   x.x.x.x con cada octeto 0-255
    valid_hostname(s) -> bool   convencion Cisco: empieza por letra, letras/
                                digitos/guiones, sin guion final, max 63
"""

import re

_DOTTED_QUAD = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")


def valid_ipish(s):
    if not _DOTTED_QUAD.match(s):
        return False
    return all(0 <= int(o) <= 255 for o in s.split("."))


def valid_hostname(s):
    return bool(_HOSTNAME_RE.match(s)) and not s.endswith("-")

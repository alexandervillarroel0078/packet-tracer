"""
config_gen.py - Genera configuracion IOS de routers (interfaces + rutas
estaticas O RIP) a partir de una topologia en texto.

SOLO CALCULO: no toca Packet Tracer, no mueve el mouse, no requiere que la
topologia ya este colocada (no lee topologia_actual.json). Reutiliza
build.parse_grouped() tal cual -- no duplica la logica de parseo de
ROUTERS/SWITCHES/RED/ENLACES/modelos.

Nota: build.py exige pyautogui instalado al importarse (aunque
parse_grouped() en si no lo usa para nada); como este modulo importa desde
build, hereda esa dependencia transitiva. El proyecto ya la trae como
requisito (requirements.txt), asi que en la practica no es un problema.

Dos modos, MUTUAMENTE EXCLUYENTES (nunca se mezclan en el mismo resultado):
    MODE_STATIC ("static"): bloque de interfaces + 'ip route' calculados
        por BFS (camino mas corto en saltos) sobre el grafo de ENLACES,
        con balanceo de carga si hay 2+ caminos de igual longitud. Sin
        ningun 'router rip'.
    MODE_RIP ("rip"): bloque de interfaces + 'router rip' (version 2, una
        'network' por cada red CLASICA distinta, no auto-summary). Sin
        ningun 'ip route'.

El desempate de rutas con costo igual (balanceo) sigue el ORDEN DE
DECLARACION en 'ENLACES:' (no alfabetico) -- mas predecible al comparar
contra el texto de la topologia.

Uso:
    from config_gen import generate_all_configs, MODE_STATIC, MODE_RIP
    configs, warnings = generate_all_configs(texto, MODE_STATIC)
    # configs: {"R01": "=== Configuracion ESTATICA -- R01 ===\n...", ...}
"""

from build import parse_grouped, TopologyError  # noqa: F401  (TopologyError se re-expone)

MODE_STATIC = "static"
MODE_RIP = "rip"


def build_router_graph(parsed):
    """
    A partir de 'parsed' (build.parse_grouped), arma:
        neighbors: {router: [{"vecino","ip_local","ip_vecino","mascara","iface"}, ...]}
                   en el ORDEN de declaracion de 'ENLACES:'.
        lan_owned: {router: [{"red","cidr","network","iface","ip","mascara"}, ...]}
        warnings:  avisos no fatales (ej. RED sin router declarado).
    """
    neighbors = {r: [] for r in parsed["routers"]}
    for enl in parsed.get("enlaces", []):
        neighbors[enl["r1"]].append({"vecino": enl["r2"], "ip_local": enl["ip1"],
                                     "ip_vecino": enl["ip2"], "mascara": enl["mascara"],
                                     "iface": enl["if1"]})
        neighbors[enl["r2"]].append({"vecino": enl["r1"], "ip_local": enl["ip2"],
                                     "ip_vecino": enl["ip1"], "mascara": enl["mascara"],
                                     "iface": enl["if2"]})

    lan_owned = {r: [] for r in parsed["routers"]}
    warnings = []
    for red in parsed.get("redes", []):
        if not red["router_lan"]:
            warnings.append(f"RED {red['nombre']}: sin router declarado (ni token "
                            f"inline ni conector); no se genera configuracion para "
                            f"esta red.")
            continue
        net = red["network"]
        lan_owned[red["router_lan"]].append({
            "red": red["nombre"], "cidr": red["cidr"], "network": net,
            "iface": red["iface_lan"], "ip": str(net.network_address + 1),
            "mascara": str(net.netmask),
        })
    return neighbors, lan_owned, warnings


def bfs_first_hops(neighbors, source):
    """
    BFS desde 'source' sobre el grafo de routers (arista = un 'ENLACES:').
    Devuelve (dist, first_hops):
        dist[nodo]       = distancia minima en SALTOS desde 'source'.
        first_hops[nodo] = set de vecinos DIRECTOS de 'source' que estan
            sobre AL MENOS UN camino minimo hacia 'nodo' -- el empate es
            exactamente el caso de balanceo de carga en rutas estaticas.
    Para 'source' mismo: dist=0, first_hops=set() (no aplica).
    """
    dist, first_hops, queue = {source: 0}, {source: set()}, [source]
    qi = 0
    while qi < len(queue):
        u = queue[qi]
        qi += 1
        for edge in neighbors.get(u, []):
            v = edge["vecino"]
            nd = dist[u] + 1
            via = {v} if u == source else set(first_hops[u])
            if v not in dist:
                dist[v] = nd
                first_hops[v] = set(via)
                queue.append(v)
            elif dist[v] == nd:
                first_hops[v] |= via
    return dist, first_hops


def _neighbor_declaration_order(neighbors, router):
    """Vecinos DIRECTOS de 'router', en el orden en que aparecen por
    primera vez en 'ENLACES:' (sin duplicados)."""
    order, seen = [], set()
    for edge in neighbors.get(router, []):
        v = edge["vecino"]
        if v not in seen:
            seen.add(v)
            order.append(v)
    return order


def compute_static_routes(parsed):
    """
    Devuelve (routes, warnings).
        routes: {router: [{"cidr","network_addr","mascara","next_hops":[ip,...]}, ...]}
    Una entrada por CADA red LAN ajena (no las propias, ya conectadas
    directo). 'next_hops' trae 2+ IPs cuando hay caminos de igual longitud
    (balanceo de carga), en el ORDEN DE DECLARACION de 'ENLACES:'.
    """
    neighbors, lan_owned, warnings = build_router_graph(parsed)
    routes = {r: [] for r in parsed["routers"]}
    for src in parsed["routers"]:
        dist, first_hops = bfs_first_hops(neighbors, src)
        ip_of_neighbor = {e["vecino"]: e["ip_vecino"] for e in neighbors[src]}
        neighbor_order = _neighbor_declaration_order(neighbors, src)
        for dst in parsed["routers"]:
            if dst == src:
                continue
            dst_lans = lan_owned.get(dst, [])
            if not dst_lans:
                continue
            if dst not in dist:
                warnings.append(f"{src}: sin camino hacia {dst} (red desconectada); "
                                f"no se genera ruta a su(s) red(es).")
                continue
            ordered_hops = [n for n in neighbor_order if n in first_hops[dst]]
            next_hops = [ip_of_neighbor[h] for h in ordered_hops]
            for lan in dst_lans:
                routes[src].append({
                    "cidr": lan["cidr"], "mascara": lan["mascara"],
                    "network_addr": str(lan["network"].network_address),
                    "next_hops": next_hops,
                })
    return routes, warnings


def classful_network(ip_str):
    """Red CLASICA (A/B/C) que contiene 'ip_str' -- el comando 'network'
    de RIP en IOS no acepta mascara, siempre trabaja en terminos clasicos."""
    octets = ip_str.split(".")
    first = int(octets[0])
    if first < 128:
        return f"{octets[0]}.0.0.0"
    if first < 192:
        return f"{octets[0]}.{octets[1]}.0.0"
    return f"{octets[0]}.{octets[1]}.{octets[2]}.0"


def compute_rip_networks(parsed):
    """
    Devuelve {router: [red_clasica, ...]} -- una linea 'network' por cada
    red CLASICA distinta entre TODAS las interfaces del router (LAN +
    enlaces), sin duplicados, en el orden en que se detectan (LAN primero,
    despues enlaces en orden de declaracion).
    """
    neighbors, lan_owned, _ = build_router_graph(parsed)
    result = {}
    for r in parsed["routers"]:
        seen, out = set(), []
        ips = [lan["ip"] for lan in lan_owned.get(r, [])]
        ips += [e["ip_local"] for e in neighbors.get(r, [])]
        for ip in ips:
            c = classful_network(ip)
            if c not in seen:
                seen.add(c)
                out.append(c)
        result[r] = out
    return result


def render_router_config(router, mode, neighbors, lan_owned, static_routes, rip_networks):
    """
    Arma el texto completo de UN router: encabezado inequivoco con el modo,
    hostname, bloque de interfaces (SIEMPRE, comun a ambos modos), y SOLO
    el bloque del modo elegido ('ip route' o 'router rip' -- nunca ambos).
    """
    etiqueta = "ESTATICA" if mode == MODE_STATIC else "RIP"
    lines = [f"=== Configuracion {etiqueta} -- {router} ===",
             f"hostname {router}", "!"]

    for lan in lan_owned.get(router, []):
        lines.append(f"interface {lan['iface']}")
        lines.append(f" ip address {lan['ip']} {lan['mascara']}")
        lines.append(" no shutdown")
    for edge in neighbors.get(router, []):
        lines.append(f"interface {edge['iface']}")
        lines.append(f" ip address {edge['ip_local']} {edge['mascara']}")
        lines.append(" no shutdown")
    lines.append("!")

    if mode == MODE_STATIC:
        for rt in static_routes.get(router, []):
            for nh in rt["next_hops"]:
                lines.append(f"ip route {rt['network_addr']} {rt['mascara']} {nh}")
    else:
        lines.append("router rip")
        lines.append(" version 2")
        for net in rip_networks.get(router, []):
            lines.append(f" network {net}")
        lines.append(" no auto-summary")

    lines.append("end")
    return "\n".join(lines)


def generate_all_configs(text, mode):
    """
    Punto de entrada principal. 'mode' es MODE_STATIC o MODE_RIP (nunca
    los dos a la vez). Devuelve (configs, warnings):
        configs: {router: texto_completo}  en el orden declarado en ROUTERS:
        warnings: avisos no fatales acumulados (redes sin router, sin
                  camino, etc.) -- no bloquean la generacion del resto.

    Lanza TopologyError (de build.parse_grouped) si el texto no es una
    topologia valida -- el llamador decide como mostrarlo.
    """
    if mode not in (MODE_STATIC, MODE_RIP):
        raise ValueError(f"mode debe ser '{MODE_STATIC}' o '{MODE_RIP}', no '{mode}'.")

    parsed = parse_grouped(text)
    neighbors, lan_owned, warnings = build_router_graph(parsed)

    if not parsed["routers"]:
        return {}, warnings + ["La topologia no declara ningun router."]

    if mode == MODE_STATIC:
        static_routes, w2 = compute_static_routes(parsed)
        rip_networks = {}
        warnings += w2
    else:
        static_routes = {}
        rip_networks = compute_rip_networks(parsed)

    configs = {}
    for router in parsed["routers"]:
        configs[router] = render_router_config(
            router, mode, neighbors, lan_owned, static_routes, rip_networks)
    return configs, warnings

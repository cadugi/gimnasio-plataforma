#!/usr/bin/env python3
"""Genera las ilustraciones del tutorial «Añadir al móvil» (SVG simples, sin marcas ajenas). Uso: scripts/make_guia_svgs.py"""
import os
OUT = os.path.join(os.path.dirname(__file__), "..", "web", "public", "img", "guia")
BG, SCREEN, INK, LIME, ORANGE, GREY = "#0a0d0a", "#f4f6f3", "#111", "#22f03a", "#ff8000", "#c9d0c8"

def svg(body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 420" role="img" aria-label="{label}">'
            f'<rect width="320" height="420" rx="18" fill="#161c16"/>'
            f'<rect x="70" y="14" width="180" height="392" rx="26" fill="#222" stroke="#555" stroke-width="3"/>'
            f'<rect x="78" y="34" width="164" height="352" rx="10" fill="{SCREEN}"/>{body}</svg>')

def hl(cx, cy, r=26):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ORANGE}" stroke-width="5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r+9}" fill="none" stroke="{ORANGE}" stroke-width="2" opacity=".5"/>')

def arrow(x1, y1, x2, y2):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{ORANGE}" stroke-width="5" stroke-linecap="round" marker-end="url(#a)"/>'
DEFS = f'<defs><marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="{ORANGE}"/></marker></defs>'
def t(x, y, s, size=13, w=700, fill=INK, anchor="middle"):
    return f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}">{s}</text>'
def bar(y, label):
    return f'<rect x="86" y="{y}" width="148" height="26" rx="13" fill="#e2e6e1"/>{t(160,y+17,label,11,600,"#333")}'
def logo(x, y, s=44):
    return f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="10" fill="#0a0d0a" stroke="{LIME}" stroke-width="3"/>{t(x+s/2,y+s/2+6,"TF",s*.4,800,LIME)}'

G = {}
# iPhone
G["ios-1-safari"] = svg(DEFS + t(160, 70, "Abre esta página", 14) + t(160, 90, "con Safari", 14) +
    '<circle cx="160" cy="170" r="46" fill="#fff" stroke="#2a7de1" stroke-width="5"/><path d="M160 170 L178 140 L142 200 Z" fill="#2a7de1"/><circle cx="160" cy="170" r="5" fill="#fff"/>' +
    t(160, 250, "Safari", 18, 800, "#2a7de1") + t(160, 290, "(la brújula azul)", 12, 600, "#555") + hl(160, 170, 58), "Icono azul de Safari, el navegador del iPhone")
G["ios-2-compartir"] = svg(DEFS + bar(46, "whatsapp.gimnasio.example") +
    f'<rect x="78" y="338" width="164" height="48" fill="#e9ece8"/><g stroke="#2a7de1" stroke-width="3" fill="none" stroke-linecap="round"><path d="M160 366 V346 M152 354 L160 346 L168 354"/><path d="M150 358 H146 V376 H174 V358 H170"/></g>' +
    t(160, 160, "Top Fitness", 20, 800) + t(160, 190, "Reserva de clases", 13, 600, "#555") + hl(160, 360, 30) + arrow(210, 250, 178, 330), "Botón Compartir, un cuadrado con una flecha hacia arriba, abajo en el centro de la pantalla")
G["ios-3-anadir"] = svg(DEFS + '<rect x="78" y="120" width="164" height="266" rx="14" fill="#eef0ed"/>' +
    t(160, 148, "Compartir", 13, 700) + '<rect x="90" y="162" width="140" height="34" rx="8" fill="#fff"/>' + t(160, 184, "Copiar", 12, 600, "#444") +
    f'<rect x="90" y="206" width="140" height="40" rx="8" fill="#fff" stroke="{ORANGE}" stroke-width="4"/><rect x="100" y="215" width="20" height="20" rx="4" fill="none" stroke="#111" stroke-width="2.5"/><path d="M110 220 V230 M105 225 H115" stroke="#111" stroke-width="2.5"/>' + t(176, 232, "Añadir a", 12, 700, INK, "start").replace('x="176"', 'x="128"') + t(128, 245, "", 1) +
    '<rect x="90" y="256" width="140" height="34" rx="8" fill="#fff"/>' + t(160, 278, "Buscar en la página", 11, 600, "#444") + arrow(250, 226, 238, 226).replace("M250", "M262") +
    t(160, 62, "Desliza hacia arriba", 12, 700, "#555") + t(160, 78, "y pulsa:", 12, 700, "#555"), "Opción Añadir a pantalla de inicio dentro del menú Compartir")
G["ios-3-anadir"] = G["ios-3-anadir"].replace(">Añadir a<", ">Añadir a pantalla<").replace('font-size="12" font-weight="700" fill="#111" text-anchor="start"', 'font-size="11" font-weight="700" fill="#111" text-anchor="start"')
G["ios-4-icono"] = svg(DEFS + '<rect x="78" y="34" width="164" height="352" rx="10" fill="#2b3a55"/>' +
    logo(98, 70) + t(120, 130, "Top Fitness", 10, 700, "#fff") + '<rect x="176" y="70" width="44" height="44" rx="10" fill="#6b7a99"/><rect x="98" y="150" width="44" height="44" rx="10" fill="#6b7a99"/><rect x="176" y="150" width="44" height="44" rx="10" fill="#6b7a99"/>' +
    hl(120, 92, 36) + t(160, 300, "Abre Top Fitness", 14, 800, "#fff") + t(160, 320, "desde este icono", 14, 800, "#fff"), "Icono verde y negro de Top Fitness en la pantalla de inicio del iPhone")
# Android
G["android-1-menu"] = svg(DEFS + bar(46, "whatsapp.gimnasio.example") +
    f'<g fill="#333"><circle cx="222" cy="59" r="2.6"/><circle cx="222" cy="66" r="2.6"/><circle cx="222" cy="52" r="2.6"/></g>' +
    t(160, 160, "Top Fitness", 20, 800) + t(160, 190, "Reserva de clases", 13, 600, "#555") + hl(222, 59, 20) + arrow(190, 130, 214, 84).replace("M190", "M180") + t(160, 330, "Pulsa los tres puntitos", 12, 700, "#555"), "Los tres puntos del menú del navegador, arriba a la derecha")
G["android-2-instalar"] = svg(DEFS + '<rect x="100" y="48" width="134" height="190" rx="10" fill="#fff" stroke="#bbb" stroke-width="2"/>' +
    t(167, 72, "Nueva pestaña", 11, 600, "#444") + t(167, 98, "Historial", 11, 600, "#444") +
    f'<rect x="106" y="112" width="122" height="44" rx="8" fill="#fff" stroke="{ORANGE}" stroke-width="4"/>' + t(167, 130, "Instalar aplicación", 11, 800) + t(167, 146, "o Añadir a inicio", 10, 700, "#555") +
    t(167, 184, "Ajustes", 11, 600, "#444") + t(167, 210, "Ayuda", 11, 600, "#444") + hl(167, 134, 0).replace('r="0"', 'r="1"') +
    t(160, 290, "Busca esta opción", 13, 700, "#555") + t(160, 308, "y púlsala", 13, 700, "#555"), "Opción Instalar aplicación o Añadir a pantalla de inicio en el menú")
G["android-3-icono"] = svg(DEFS + '<rect x="78" y="34" width="164" height="352" rx="10" fill="#1d3b34"/>' +
    logo(98, 70) + t(120, 130, "Top Fitness", 10, 700, "#fff") + '<rect x="176" y="70" width="44" height="44" rx="22" fill="#4f7c70"/><rect x="98" y="150" width="44" height="44" rx="22" fill="#4f7c70"/><rect x="176" y="150" width="44" height="44" rx="22" fill="#4f7c70"/>' +
    hl(120, 92, 36) + t(160, 300, "Abre Top Fitness", 14, 800, "#fff") + t(160, 320, "desde este icono", 14, 800, "#fff"), "Icono verde y negro de Top Fitness en la pantalla de inicio del móvil Android")
G["permisos"] = svg(DEFS + '<rect x="88" y="120" width="144" height="150" rx="14" fill="#fff" stroke="#bbb" stroke-width="2"/>' +
    t(160, 150, "whatsapp.gimnasio.example", 11, 700) + t(160, 172, "quiere enviarte", 11, 600, "#444") + t(160, 188, "avisos", 11, 600, "#444") +
    f'<rect x="100" y="204" width="56" height="40" rx="8" fill="#e2e6e1"/>{t(128,229,"No",13,700)}<rect x="164" y="204" width="56" height="40" rx="8" fill="{LIME}" stroke="{ORANGE}" stroke-width="4"/>{t(192,229,"Permitir",11,800)}', "Ventana del móvil que pregunta si permites los avisos; hay que pulsar Permitir")
os.makedirs(OUT, exist_ok=True)
for name, s in G.items():
    open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8").write(s)
print(len(G), "ilustraciones")

"""Genera assets/whatsapp-booking-flow.json (Flow de reservas de Top Fitness).

Meta no permite colores, fuentes ni modo oscuro propios dentro de un Flow: lo pinta
WhatsApp según el tema del móvil. La marca (negro y verde neón) va en las imágenes.

Uso: python3 scripts/build_booking_flow.py
"""
import base64
import io
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'


def jpeg(path, size, quality=84):
    image = Image.open(path).convert('RGB')
    image.thumbnail(size, Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=quality, optimize=True, progressive=False)
    return base64.b64encode(out.getvalue()).decode()


def prop(kind, example, **extra):
    return dict({'type': kind, '__example__': example}, **extra)


def options(example_id='1'):
    return {'type': 'array', 'items': {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'title': {'type': 'string'}, 'description': {'type': 'string'}}},
        '__example__': [{'id': example_id, 'title': 'Ejemplo', 'description': 'Dato ficticio'}]}


COMMON = {'error': prop('string', ''), 'has_error': prop('boolean', False), 'error_message': prop('string', '')}


def screen(name, title, data, children, terminal=False):
    result = {'id': name, 'title': title, 'data': dict(data, **COMMON),
              'layout': {'type': 'SingleColumnLayout', 'children': [{'type': 'Form', 'name': 'form', 'children': children}]}}
    if terminal:
        result.update(terminal=True, success=True)
    return result


def step_header(heading):
    return [{'type': 'TextCaption', 'text': '${data.step}'}, {'type': 'TextHeading', 'text': heading}]


NOTICE = {'type': 'TextBody', 'text': '${data.error}', 'visible': '${data.has_error}', 'font-weight': 'bold'}


def exchange(label, payload, enabled='${data.has_choices}'):
    return {'type': 'Footer', 'label': label, 'enabled': enabled,
            'on-click-action': {'name': 'data_exchange', 'payload': payload}}


def build():
    banner = jpeg(ASSETS / 'topfitness-bienvenida.png', (640, 360))
    logo = jpeg(ASSETS / 'topfitness-logo.png', (160, 160))
    screens = [
        screen('START', 'Reservar clase',
               {'step': prop('string', '1 de 4'), 'detail': prop('string', 'Elige la actividad que quieres hacer.'),
                'people': options(), 'person_default': prop('string', '1'), 'show_person': prop('boolean', False),
                'activities': options(), 'has_choices': prop('boolean', True)},
               [{'type': 'Image', 'src': banner, 'width': 320, 'height': 180, 'scale-type': 'contain', 'alt-text': 'Top Fitness · Reserva tu clase'},
                {'type': 'TextCaption', 'text': '${data.step}'},
                {'type': 'TextHeading', 'text': 'Reserva tu clase'},
                {'type': 'TextBody', 'text': '${data.detail}'}, NOTICE,
                {'type': 'Dropdown', 'name': 'person', 'label': 'Persona', 'required': False, 'data-source': '${data.people}',
                 'visible': '${data.show_person}'},
                {'type': 'Dropdown', 'name': 'activity', 'label': 'Actividad', 'required': True,
                 'data-source': '${data.activities}', 'enabled': '${data.has_choices}'},
                exchange('Elegir día', {'person': '${form.person}', 'activity': '${form.activity}'})]),
        screen('DAY', 'Elige el día',
               {'step': prop('string', '2 de 4'), 'detail': prop('string', 'Actividad'), 'days': options(),
                'has_choices': prop('boolean', True)},
               step_header('¿Qué día?') + [{'type': 'TextBody', 'text': '${data.detail}'}, NOTICE,
                {'type': 'RadioButtonsGroup', 'name': 'choice', 'label': 'Día', 'required': True,
                 'data-source': '${data.days}', 'enabled': '${data.has_choices}'},
                exchange('Ver horarios', {'choice': '${form.choice}'})]),
        screen('SLOT', 'Elige la hora',
               {'step': prop('string', '3 de 4'), 'detail': prop('string', 'Actividad · Lunes 01-01'), 'slots': options(),
                'has_choices': prop('boolean', True)},
               step_header('¿A qué hora?') + [{'type': 'TextBody', 'text': '${data.detail}'}, NOTICE,
                {'type': 'RadioButtonsGroup', 'name': 'choice', 'label': 'Horario', 'required': True,
                 'data-source': '${data.slots}', 'enabled': '${data.has_choices}'},
                exchange('Revisar', {'choice': '${form.choice}'})]),
        screen('CONFIRM', 'Confirmar',
               {'step': prop('string', '4 de 4'), 'headline': prop('string', 'Actividad'), 'when': prop('string', 'Lunes 01-01 · 18:00'),
                'who': prop('string', 'Nombre'), 'note': prop('string', 'Tu plaza se confirma en cuanto pulses el botón.'),
                'cta': prop('string', 'Confirmar reserva'), 'can_confirm': prop('boolean', True)},
               step_header('Revisa y confirma') + [
                {'type': 'TextSubheading', 'text': '${data.headline}'},
                {'type': 'TextBody', 'text': '${data.when}'},
                {'type': 'TextBody', 'text': '${data.who}'},
                {'type': 'TextBody', 'text': '${data.note}'}, NOTICE,
                {'type': 'Footer', 'label': 'Confirmar', 'enabled': '${data.can_confirm}',
                 'on-click-action': {'name': 'data_exchange', 'payload': {'confirm': True}}}]),
        screen('DONE', 'Listo',
               {'headline': prop('string', 'Reserva confirmada'), 'detail': prop('string', 'Actividad\nLunes 01-01 · 18:00\nNombre'),
                'flow_token': prop('string', 'token')},
               [{'type': 'Image', 'src': logo, 'width': 96, 'height': 96, 'scale-type': 'contain', 'alt-text': 'Top Fitness'},
                {'type': 'TextHeading', 'text': '${data.headline}'},
                {'type': 'TextBody', 'text': '${data.detail}'},
                {'type': 'Footer', 'label': 'Volver al chat',
                 'on-click-action': {'name': 'complete', 'payload': {'flow_token': '${data.flow_token}'}}}], terminal=True),
    ]
    return {'version': '7.1', 'data_api_version': '3.0',
            'routing_model': {'START': ['DAY'], 'DAY': ['SLOT'], 'SLOT': ['CONFIRM'], 'CONFIRM': ['DONE'], 'DONE': []},
            'screens': screens}


if __name__ == '__main__':
    flow = build()
    target = ASSETS / 'whatsapp-booking-flow.json'
    target.write_text(json.dumps(flow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{target} · {target.stat().st_size // 1024} KB')

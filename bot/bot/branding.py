"""Presentación Telegram; no cambia autorizaciones ni reglas de reserva."""
from datetime import date
from html import escape
from pathlib import Path
import re
from .transport import Rejected

ROOT = Path(__file__).resolve().parents[1]
BANNER = ROOT / 'assets' / 'topfitness-bienvenida.png'


def date_label(value):
    try:
        day = date.fromisoformat(value)
    except (ValueError, TypeError):
        return str(value)
    return day.strftime('%d-%m-%Y')


def display_dates(text):
    text=re.sub(r'\b\d{4}-\d{2}-\d{2}\b',lambda match:date_label(match[0]),str(text))
    return re.sub(r'\b(\d{2})/(\d{2})/(\d{4})\b',r'\1-\2-\3',text)


def button_appearance(text, action):
    text = display_dates(text)
    kind = action.get('kind')
    icons = {'dates': '📅', 'reserved': '🎟', 'waiting': '⏳', 'people': '👥',
             'help': '❔', 'notifications': '🔔', 'person': '👤', 'review': '🏋️',
             'calendar': '📆', 'calendar_ics': '📲', 'calendar_image': '🗓',
             'portable_favorites': '⭐', 'portable_routines': '🔁', 'portable_summary': '📋',
             'portable_human': '💬', 'portable_human_resume': '🤖', 'portable_guide': '❔',
             'portable_move_dates': '🔄', 'portable_move_confirm': '✓',
             'portable_routine_dates': '➕', 'portable_routine_plan': '📅',
             'portable_favorite_sessions': '🏋️', 'portable_booking': '🎟',
             'review_cancel': '↗', 'confirm_reserve': '✓', 'confirm_cancel': '✕',
             'accept_offer': '✓', 'decline_offer': '✕', 'show_offer': '🎟'}
    if kind == 'schedules':
        text = '📅 ' + date_label(action.get('fecha', text))
    elif kind in ('menu', 'back'):
        text = '‹ Menú'
    elif kind in icons and not text.startswith((icons[kind], '★', '☆', '↻', '👤')):
        text = icons[kind] + ' ' + text
    fields = {'text': text}
    if kind in ('reserved','waiting','people','person','review','schedules','calendar','calendar_image',
                'portable_favorites','portable_routines','portable_summary','portable_human',
                'portable_move_dates','portable_move_sessions','portable_move_review','portable_booking',
                'portable_routine_dates','portable_routine_sessions','portable_routine_plan','portable_favorite_sessions',
                'portable_search','portable_alternatives','channel_demo'):
        fields['style'] = 'primary'
    if kind in ('dates', 'confirm_reserve', 'accept_offer', 'calendar_ics','portable_move_confirm','portable_human_resume'):
        fields['style'] = 'success'
    if kind=='confirm_reserve' and action.get('accept_waitlist'):
        fields['style']='primary'
    if kind in ('confirm_cancel', 'decline_offer', 'review_cancel','channel_real'):
        fields['style'] = 'danger'
    if kind in ('portable_routine_set','portable_week_set','portable_favorite_set'):
        fields['style']='success' if action.get('enabled') else 'danger'
    if kind == 'set_notifications':
        enabled = action.get('reminder_24h') or action.get('reminder_1h')
        fields['text'] = ('🔔 ' if enabled else '🔕 ') + text
        fields['style']='success' if enabled and not text.casefold().startswith('desactivar') else 'danger'
    return fields


def message(text, buttons=(), pilot=False, layout=None):
    text = display_dates(text)
    header = '🟢 <b>TOPFITNESS</b>\n\n'
    if pilot:
        header += '<b>PRUEBA EN PRODUCCIÓN · Plazas reales</b>\n\n'
    buttons = list(buttons)
    if layout == 'menu':
        rows = [buttons[:1]] + [buttons[i:i+2] for i in range(1,len(buttons),2)]
    elif layout == 'dates':
        days = buttons[:-1]
        rows = [days[i:i + 2] for i in range(0, len(days), 2)] + [buttons[-1:]]
    else:
        rows = [[b] for b in buttons]
    return {'text': header + escape(str(text)), 'parse_mode': 'HTML',
            'reply_markup': {'inline_keyboard': [row for row in rows if row]}}


def send_reply(telegram, user, reply, welcome=False):
    if reply.get('attachment'):
        from .calendar_export import attachment_bytes
        payload={k:v for k,v in reply.items() if k not in ('attachment','attachment_scope')}
        try:name,mime,content=attachment_bytes(reply['attachment'],ROOT)
        except Rejected as error:
            if error.code!='CALENDAR_IMAGE_UNAVAILABLE':raise
            payload['text']='No se pudo generar la imagen. Puedes volver a Mi calendario y descargar el archivo ICS.'
            return telegram.call('sendMessage',chat_id=int(user),**payload)
        payload['caption']=payload.pop('text')
        method,field=('sendPhoto','photo') if mime=='image/png' else ('sendDocument','document')
        return telegram.upload_bytes(method,field,name,content,mime,chat_id=int(user),**payload)
    # The banner is sent only in response to an authorized /start. Never to callbacks.
    # Keep TemporaryFailure retryable: don't fall back after an uncertain delivery.
    if welcome and BANNER.is_file() and len(reply.get('text', '')) <= 1024:
        payload = dict(reply)
        payload['caption'] = payload.pop('text')
        try:
            return telegram.upload('sendPhoto', {'photo': BANNER}, chat_id=int(user), **payload)
        except Rejected as error:
            if error.code != 'TELEGRAM_400':
                raise
        except OSError:
            pass
    return telegram.call('sendMessage', chat_id=int(user), **reply)

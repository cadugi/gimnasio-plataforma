"""Calendario personal: instantáneas privadas, iCalendar y PNG sin servicios de IA."""
from datetime import date, datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from .transport import Rejected


def confirmed(bookings, person, now):
    current=datetime.fromisoformat(now).replace(tzinfo=None)
    out=[]
    for b in bookings:
        if b.get('estado')!='RESERVED' or int(b['persona_id'])!=person: continue
        if not re.fullmatch(r'\d{2}:\d{2}-\d{2}:\d{2}',b['hora']): raise Rejected('INVALID_SCHEDULE')
        start=datetime.fromisoformat(b['fecha']+'T'+b['hora'][:5])
        end=datetime.fromisoformat(b['fecha']+'T'+b['hora'][6:])
        if end<=start: raise Rejected('INVALID_SCHEDULE')
        if start>current:
            out.append({k:b[k] for k in ('id','persona_id','horario_id','fecha','hora','clase','version')})
    if len(out)>50: raise Rejected('CALENDAR_TOO_LARGE')
    return sorted(out,key=lambda b:(b['fecha'],b['hora'],b['id']))


def monday(day):
    d=date.fromisoformat(day)
    return d-timedelta(days=d.weekday())


def _escape(value):
    return str(value).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n',r'\n').replace(';',r'\;').replace(',',r'\,').replace('\x00','')


def _fold(line):
    # RFC 5545: at most 75 octets, including continuation whitespace; never split UTF-8.
    lines=[];part='';size=0
    for c in line:
        width=len(c.encode('utf-8'))
        if size+width>75: lines.append(part);part=' ';size=1
        part+=c;size+=width
    lines.append(part)
    return '\r\n'.join(lines)


def calendar_bytes(snapshot):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//TopFitness//Reservas//ES','CALSCALE:GREGORIAN','METHOD:PUBLISH',
           'X-WR-CALNAME:TopFitness - Mis reservas','X-WR-TIMEZONE:Europe/Madrid',
           'BEGIN:VTIMEZONE','TZID:Europe/Madrid',
           'BEGIN:DAYLIGHT','DTSTART:19960331T020000','RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU','TZOFFSETFROM:+0100','TZOFFSETTO:+0200','TZNAME:CEST','END:DAYLIGHT',
           'BEGIN:STANDARD','DTSTART:19961027T030000','RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU','TZOFFSETFROM:+0200','TZOFFSETTO:+0100','TZNAME:CET','END:STANDARD','END:VTIMEZONE']
    stamp=datetime.fromisoformat(snapshot['generated_at']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for b in snapshot['bookings']:
        uid=hashlib.sha256((snapshot['namespace']+':'+str(b['id'])+':'+b['fecha']+':'+str(b['horario_id'])).encode()).hexdigest()
        start=b['fecha'].replace('-','')+'T'+b['hora'][:5].replace(':','')+'00'
        end=b['fecha'].replace('-','')+'T'+b['hora'][6:].replace(':','')+'00'
        lines+=['BEGIN:VEVENT','UID:'+uid+'@reservas.topfitness.invalid','DTSTAMP:'+stamp,
                'DTSTART;TZID=Europe/Madrid:'+start,'DTEND;TZID=Europe/Madrid:'+end,
                'SEQUENCE:'+str(int(b['version'])),'SUMMARY:'+_escape('TopFitness · '+b['clase']),
                'LOCATION:TopFitness','STATUS:CONFIRMED','TRANSP:OPAQUE',
                'DESCRIPTION:'+_escape('Reserva confirmada. Copia puntual: consulta el bot para cambios o cancelaciones. Elimina del calendario las clases que canceles.'),'END:VEVENT']
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(_fold(line) for line in lines)+'\r\n').encode('utf-8')


def render_timetable(snapshot, root):
    """Windows uses installed GDI+; no installation, shell interpolation or temporary image."""
    week=date.fromisoformat(snapshot['week'])
    days=[]
    for i,name in enumerate(('Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo')):
        d=week+timedelta(days=i)
        days.append({'day':name,'date':d.strftime('%d-%m-%Y'),'items':[{'class':b['clase'],'time':b['hora']} for b in snapshot['bookings'] if b['fecha']==d.isoformat()]})
    data={'name':snapshot['name'],'days':days,'from':week.strftime('%d-%m-%Y'),'until':(week+timedelta(days=6)).strftime('%d-%m-%Y'),
          'generated':datetime.fromisoformat(snapshot['generated_at']).strftime('%d-%m-%Y %H:%M'),'demo':snapshot.get('demo',False),
          'logo':str(Path(root)/'assets/topfitness-logo.png')}
    if os.name!='nt': return _pillow_timetable(data)
    try:
        script=(Path(root)/'scripts/render_calendar.ps1').read_text(encoding='utf-8')
        run=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],
                           input=json.dumps(data,ensure_ascii=True),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.SubprocessError):raise Rejected('CALENDAR_IMAGE_UNAVAILABLE') from None
    if run.returncode: raise Rejected('CALENDAR_IMAGE_UNAVAILABLE')
    try: result=base64.b64decode(run.stdout.strip(),validate=True)
    except (ValueError,TypeError): raise Rejected('CALENDAR_IMAGE_UNAVAILABLE') from None
    if not result.startswith(b'\x89PNG\r\n\x1a\n') or len(result)>5*1024*1024: raise Rejected('CALENDAR_IMAGE_UNAVAILABLE')
    return result


def _pillow_timetable(data):
    # Optional non-Windows deployment engine; never installs its own dependencies.
    try:
        from PIL import Image,ImageDraw,ImageFont
        from io import BytesIO
    except ImportError: raise Rejected('CALENDAR_IMAGE_UNAVAILABLE') from None
    heights=[max(145,25+len(d['items'])*46) for d in data['days']]
    image=Image.new('RGB',(1080,290+sum(heights)),(12,15,14));draw=ImageDraw.Draw(image)
    def font(size):
        for file in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'):
            if Path(file).is_file(): return ImageFont.truetype(file,size)
        return ImageFont.load_default(size=size)
    draw.rectangle((0,0,1080,8),fill='#00ed49')
    with Image.open(data['logo']) as logo:
        logo=logo.convert('RGB');logo.thumbnail((160,160));image.paste(logo,(40,32))
    draw.text((235,36),'MI CALENDARIO',font=font(43),fill='white')
    draw.text((235,96),data['from']+'  /  '+data['until'],font=font(25),fill='#00ed49')
    draw.text((235,140),data['name'][:42],font=font(24),fill='#c4cec8')
    y=220
    for day,height in zip(data['days'],heights):
        draw.rounded_rectangle((32,y,1048,y+height-10),12,fill='#181e1a')
        draw.text((54,y+25),day['day'],font=font(27),fill='white')
        draw.text((54,y+67),day['date'],font=font(20),fill='#97ab9e')
        for n,item in enumerate(day['items']):
            yy=y+18+n*46
            draw.rectangle((250,yy+3,255,yy+36),fill='#00ed49')
            draw.text((273,yy),item['time']+'  |  '+item['class'][:28],font=font(24),fill='#e9f7ed')
        if not day['items']:draw.text((273,y+48),'Sin reservas',font=font(23),fill='#7e9185')
        y+=height
    draw.text((40,y+15),('DEMO  |  ' if data['demo'] else '')+'Solo confirmadas  |  Hora de Madrid  |  '+data['generated'],font=font(19),fill='#97ab9e')
    stream=BytesIO();image.save(stream,format='PNG');return stream.getvalue()


class CalendarMenu:
    def calendar_view(self,user,person,name,kind='calendar',week=None):
        data=self.backend.call(user,action='list',persona_id=person)
        if not data.get('now'): raise Rejected('CALENDAR_UNAVAILABLE')
        bookings=confirmed(data['bookings'],person,data['now'])
        back=self.button(user,person,'Menú',kind='menu')
        if not bookings:
            return self.reply('Mi calendario\nNo tienes reservas confirmadas pendientes.',[self.button(user,person,'Reservar clase',kind='dates'),back])
        namespace=self.store.c.execute("SELECT value FROM metadata WHERE key='calendar_namespace'").fetchone()
        if not namespace:
            self.store.c.execute("INSERT OR IGNORE INTO metadata VALUES ('calendar_namespace',?)",(uuid.uuid4().hex,));self.store.c.commit()
            namespace=self.store.c.execute("SELECT value FROM metadata WHERE key='calendar_namespace'").fetchone()
        snapshot={'bookings':bookings,'namespace':namespace[0],'name':name,'persona_id':person,'generated_at':data['now'],'demo':not self.pilot}
        if kind=='calendar':
            quantity='1 clase confirmada pendiente' if len(bookings)==1 else f'{len(bookings)} clases confirmadas pendientes'
            return self.reply(f'Mi calendario · {name}\n{quantity}.\n\nElige archivo o imagen.\nEs una copia puntual, sin sincronización.',[
                self.button(user,person,'Añadir al móvil',kind='calendar_ics'),self.button(user,person,'Ver horario',kind='calendar_image'),back])
        if kind=='calendar_ics':
            reply=self.reply('Abre o importa este archivo en tu calendario.\nNo se sincroniza automáticamente.',[self.button(user,person,'Mi calendario',kind='calendar')])
            reply['attachment']={'kind':'calendar_ics','snapshot':snapshot}
            return reply
        first=monday(bookings[0]['fecha']);last=monday(bookings[-1]['fecha'])
        selected=monday(week) if week else first
        if selected<first or selected>last: raise Rejected('STALE_ACTION')
        snapshot['week']=selected.isoformat()
        buttons=[]
        if selected>first:buttons.append(self.button(user,person,'‹ Semana anterior',kind='calendar_image',week=(selected-timedelta(days=7)).isoformat()))
        if selected<last:buttons.append(self.button(user,person,'Siguiente semana ›',kind='calendar_image',week=(selected+timedelta(days=7)).isoformat()))
        buttons.append(self.button(user,person,'Mi calendario',kind='calendar'))
        reply=self.reply('Tu horario · '+selected.strftime('%d-%m-%Y')+' a '+(selected+timedelta(days=6)).strftime('%d-%m-%Y')+'\nConfirmadas · Hora de Madrid · Copia puntual',buttons)
        reply['attachment']={'kind':'calendar_image','snapshot':snapshot}
        return reply

    def refresh_calendar(self,user,reply):
        if not reply.get('attachment'):return reply
        item=reply['attachment'];person=item['snapshot']['persona_id']
        people=self.backend.call(user,action='people')['people']
        name=next((p['nombre'] for p in people if int(p['id'])==person),None)
        if name is None:return self.reply('Esta persona ya no está autorizada. Abre el menú para continuar.')
        try:return self.calendar_view(user,person,name,item['kind'],item['snapshot'].get('week'))
        except Rejected as error:
            if error.code!='STALE_ACTION':raise
            return self.calendar_view(user,person,name)


def attachment_bytes(attachment,root):
    if attachment['kind']=='calendar_ics':return 'reservas-topfitness.ics','text/calendar',calendar_bytes(attachment['snapshot'])
    if attachment['kind']=='calendar_image':return 'horario-topfitness.png','image/png',render_timetable(attachment['snapshot'],root)
    if attachment['kind']=='static_image' and attachment.get('name')=='horario':
        return 'horario-topfitness.png','image/png',(root/'assets'/'topfitness-horario.png').read_bytes()
    raise ValueError('Adjunto no permitido')

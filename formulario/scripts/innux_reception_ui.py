"""Selectores comprobados en la instalación local. Nunca usa coordenadas."""
import ctypes
import datetime
import sys
from collections import deque
from pathlib import Path
from innux_reception_core import ReceptionError, require, FIELDS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'CajaGimnasio'))


def visible_controls(root):
    queue = deque([root]); count = 0
    while queue and count < 600:
        node = queue.popleft(); count += 1
        try:
            if node.element_info.control_type in {'DataGrid','Table','DataItem','List','ListItem','Tree','TreeItem'}:
                continue
            if not node.is_visible():
                continue
            yield node
            queue.extend(node.children())
        except Exception:
            continue


class SystemTime(ctypes.Structure):
    _fields_ = [(key, ctypes.c_ushort) for key in
                ('year','month','day_of_week','day','hour','minute','second','milliseconds')]


class OfficialUI:
    def __init__(self):
        self.page_handle = None

    def page(self):
        from innux_launcher import NativeInnux
        from pywinauto import Desktop
        native = NativeInnux(); root, modals = native.inspect()
        require(root and not modals, 'Abre una ficha nueva en Innux y resuelve sus ventanas pendientes.')
        main = Desktop(backend='uia').window(handle=root['handle']).wrapper_object()
        pages = [n for n in visible_controls(main) if n.element_info.automation_id == 'frmPaginaCliente']
        require(len(pages) == 1, 'Abre Clientes → Nuevo cliente en Innux.')
        page = pages[0]
        if self.page_handle is not None:
            require(page.element_info.handle == self.page_handle, 'La ficha de Innux ha cambiado.')
        return page

    def control(self, aid):
        controls = [n for n in visible_controls(self.page()) if n.element_info.automation_id == aid]
        require(len(controls) == 1 and controls[0].is_enabled(), 'Innux no presenta el campo requerido. Revisa su pantalla.')
        return controls[0]

    def attach_blank(self):
        require(ctypes.windll.shell32.IsUserAnAdmin(), 'Inicia el conector con permisos de administrador, igual que Innux.')
        page = self.page()
        self.page_handle = page.element_info.handle
        for aid in FIELDS:
            require(not self.text(aid).strip(), 'La ficha contiene datos. No se sobrescribirá: abre una ficha nueva vacía.')
        require(self.control('btnGuardar').is_enabled(), 'El guardado de Innux no está disponible.')

    def text(self, aid):
        return self.control(aid).get_value()

    def number(self):
        return self.text('edtNumero').strip()

    def set_text(self, aid, value):
        require(aid in FIELDS, 'Campo fuera de la lista permitida.')
        self.control(aid).set_edit_text(value)
        require(self.text(aid) == value, 'Innux no ha aceptado un campo completo. Revisa la ficha.')

    def date_control(self):
        from pywinauto import Desktop
        control = self.control('dateNascimento')
        return Desktop(backend='win32').window(handle=control.element_info.handle).wrapper_object()

    def set_birth(self, birth):
        d = datetime.date.fromisoformat(birth)
        self.date_control().set_time(year=d.year,month=d.month,day=d.day)

    def birth(self):
        value = self.date_control().get_time()
        return datetime.date(value.wYear, value.wMonth, value.wDay).isoformat()

    def save(self):
        # Only the exact, visible official Save button on the verified page.
        self.control('btnGuardar').invoke()

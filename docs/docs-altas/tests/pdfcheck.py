# Uso: python -I pdfcheck.py fichero.pdf fichero.expect  -> comprueba que cada línea de .expect aparece en el texto del PDF
import sys,pymupdf
t=''.join(p.get_text() for p in pymupdf.open(sys.argv[1]))
miss=[l for l in open(sys.argv[2]).read().splitlines() if l and l not in t]
print('PDFCHECK:', 'PASS' if not miss else 'FAIL faltan '+repr(miss)); sys.exit(1 if miss else 0)

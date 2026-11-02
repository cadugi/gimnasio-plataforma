#!/bin/bash
# Pruebas del remitente push (BD aislada tf_test_reservas, envío simulado).
cd "$(dirname "$0")/.." && sudo ~/work/push/venv/bin/python tests/test_push_sender.py "$@"

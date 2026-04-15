# -*- coding: utf-8 -*-
"""
conftest.py - pytest konfigurasyonu
Proje kokunu sys.path'e ekler; tum testler data/strategy/risk/broker import edebilir.
"""

import sys
import os

# Proje koku (conftest.py'nin bulundugu dizin)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

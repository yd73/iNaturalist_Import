# ==============================================================
# Plugin QGIS : iNaturalist Import
# Fichier : yd_plugin.py
# Version : 1.0.0
# Rôle    : Point d’entrée du plugin et gestion de l’interface
# QGIS    : 3.40 (Bratislava)
# Python  : 3.12
# Auteur  : Yves Durivault (avec le concours de Chatgpt).
# ==============================================================

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

# Script 1
from .yd_Script_1 import yd_run as yd_run_script_1

# Script 2
from .yd_Script_2 import yd_run as yd_run_script_2


class yd_iNaturalistImportPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        # Chemins des icônes
        icon_1_path = os.path.join(
            self.plugin_dir, "icons", "yd_icon_script_1.png"
        )
        icon_2_path = os.path.join(
            self.plugin_dir, "icons", "yd_icon_script_2.png"
        )

        # Action 1 : Script Import
        action_1 = QAction(
            QIcon(icon_1_path),
            "yd Script 1 – Import iNaturalist",
            self.iface.mainWindow()
        )
        action_1.triggered.connect(
            lambda: yd_run_script_1(self.iface)
        )

        # Action 2 : Script Taxonomie
        action_2 = QAction(
            QIcon(icon_2_path),
            "yd Script 2 – Taxonomie",
            self.iface.mainWindow()
        )
        action_2.triggered.connect(
            lambda: yd_run_script_2(self.iface)
        )

        self.iface.addToolBarIcon(action_1)
        self.iface.addToolBarIcon(action_2)

        self.actions.extend([action_1, action_2])

    def unload(self):
        for action in self.actions:
            self.iface.removeToolBarIcon(action)

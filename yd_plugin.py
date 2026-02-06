# ==============================================================
# Plugin QGIS : iNaturalist Import
# Fichier : yd_plugin.py
# Version : 2.2.0
# QGIS    : 3.28+ (Firenze, Bratislava)
# Python  : 3.12
# ==============================================================

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .yd_Script_1 import yd_run as yd_run_script_1
from .yd_Script_2 import yd_run as yd_run_script_2


class yd_iNaturalistImportPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []

        # Persistance des scripts
        self.script_1 = None
        self.script_2 = None

    # ----------------------------------------------------------
    # Initialisation GUI
    # ----------------------------------------------------------
    def initGui(self):
        icon_1_path = os.path.join(
            self.plugin_dir, "icons", "yd_icon_script_1.png"
        )
        icon_db_path = os.path.join(
            self.plugin_dir, "icons", "yd_icon_database_manager.png"
        )

        action_1 = QAction(
            QIcon(icon_1_path),
            "yd Script 1 - Import iNaturalist",
            self.iface.mainWindow()
        )
        action_1.triggered.connect(self.run_script_1)

        # v2.0.0 : Gestionnaire de Base de Donnees Taxonomique
        action_db_manager = QAction(
            QIcon(icon_db_path),
            "Taxonomy Database Manager",
            self.iface.mainWindow()
        )
        action_db_manager.triggered.connect(self.run_db_manager)

        self.iface.addToolBarIcon(action_1)
        self.iface.addToolBarIcon(action_db_manager)
        
        # Ajouter aussi dans le menu Extensions
        self.iface.addPluginToMenu("iNaturalist Import", action_db_manager)

        self.actions.extend([action_1, action_db_manager])

    # ----------------------------------------------------------
    # Lancement Script 1
    # ----------------------------------------------------------
    def run_script_1(self):
        self.script_1 = yd_run_script_1(self.iface)
        self.script_1.run()

    # ----------------------------------------------------------
    # Lancement Script 2
    # ----------------------------------------------------------
    def run_script_2(self):
        self.script_2 = yd_run_script_2(self.iface)
        self.script_2.run()

    # ----------------------------------------------------------
    # v2.0.0 : Gestionnaire de Base de Donnees Taxonomique
    # ----------------------------------------------------------
    def run_db_manager(self):
        """
        Ouvre le gestionnaire de base de donnees taxonomique mondiale.
        
        Permet de :
        - Visualiser le statut de la BDD locale
        - Telecharger/Mettre a jour la BDD mondiale
        - Voir les changements entre versions
        - Gerer les parametres
        """
        from .yd_database_manager_dialog import DatabaseManagerDialog
        
        dialog = DatabaseManagerDialog(self.plugin_dir, self.iface.mainWindow())
        dialog.exec_()

    # ----------------------------------------------------------
    # Dechargement plugin
    # ----------------------------------------------------------
    def unload(self):
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
            self.iface.removePluginMenu("iNaturalist Import", action)
        self.actions.clear()

# ==============================================================
# Plugin QGIS : iNaturalist Import
# Script     : yd_Script_1.py (Module 1)
# Rôle       : Import des observations iNaturalist
# QGIS       : 3.40 (Bratislava)
# Python     : 3.12
# ==============================================================

# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QPushButton, QDateEdit, QCheckBox,
    QWidget, QLabel, QCalendarWidget, QApplication, QProgressDialog, QProgressBar
)
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsProject, QgsCoordinateReferenceSystem

from .yd_Cercle import YD_Cercle


class yd_run:
    """Classe principale du Script 1 - Import iNaturalist"""

    def __init__(self, iface):
        self.iface = iface
        
        # Variables globales
        self.scu_origine = None
        self.latitude_centre = None
        self.longitude_centre = None
        self.rayon_metres = None
        self.nom_couche_cercle = None
        self.dossier_projet = None
        
        # Filtres d'entrée (Point 6)
        self.filter_user = None
        self.filter_taxon = None
        self.filter_date_start = None
        self.filter_date_end = None
        self.filter_month = None  # Mois spécifique (1-12) ou None
        self.filter_quality = None
        
        # Champs de sortie (Point 7)
        self.selected_fields = []
        self.field_checkboxes = {}
    
    def __del__(self):
        """Destructeur : nettoyer les ressources pour éviter les fichiers verrouillés"""
        if hasattr(self, 'step8_movie') and self.step8_movie:
            try:
                self.step8_movie.stop()
                self.step8_movie.deleteLater()
            except:
                pass

    def run(self):
        """Point d'entrée principal"""
        
        # =========================================================
        # POINT 1 : Test si module pyinaturalist présent
        # =========================================================
        try:
            import pyinaturalist
        except ImportError:
            QMessageBox.critical(
                None,
                "iNaturalist Import - ATTENTION ! Missing dependency",
                "This tool requires the Python module 'pyinaturalist'.\n"
                "To install it for QGIS:\n\n"
                "1. Close QGIS.\n"
                "2. Open the 'OSGeo4W Shell'.\n"
                "3. Run the following command:\n"
                "   python -m pip install pyinaturalist\n"
                "4. Restart QGIS.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Cet outil nécessite le module Python 'pyinaturalist'.\n"
                "Pour l'installer dans QGIS :\n\n"
                "1. Fermez QGIS.\n"
                "2. Ouvrez le « OSGeo4W Shell ».\n"
                "3. Lancez la commande suivante :\n"
                "   python -m pip install pyinaturalist\n"
                "4. Redémarrez QGIS."
            )
            return  # Sortie propre
        
        # =========================================================
        # POINT 1.5 : Vérification et Installation BDD Taxonomique
        # =========================================================
        from .yd_taxonomy_database import TaxonomyDatabase
        from .yd_database_downloader import DatabaseDownloader
        
        plugin_dir = os.path.dirname(__file__)
        db = TaxonomyDatabase(plugin_dir)
        
        if not db.is_installed():
            # BDD pas installée - Installation AUTOMATIQUE
            reply = QMessageBox.information(
                None,
                "Taxonomy Database / Base de Données Taxonomique",
                "The worldwide taxonomy database is required and will be downloaded automatically.\n"
                "This will take approximately 5 seconds.\n\n"
                "La base de données taxonomique mondiale est requise et sera téléchargée automatiquement.\n"
                "Cela prendra environ 5 secondes.",
                QMessageBox.Ok
            )
            
            # Lancer le téléchargement
            downloader = DatabaseDownloader(plugin_dir, self.iface.mainWindow())
            
            # Créer une boucle d'événements pour attendre la fin
            from qgis.PyQt.QtCore import QEventLoop
            event_loop = QEventLoop()
            
            # Dialogue de progression
            progress = QProgressDialog(
                "Downloading taxonomy database...\nTéléchargement de la base taxonomique...",
                None,
                0,
                100,
                self.iface.mainWindow()
            )
            progress.setWindowTitle("Database Download / Téléchargement BDD")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setCancelButton(None)
            progress.show()
            
            # Variable pour le résultat
            download_result = {'success': False, 'message': ''}
            
            # Connecter les signaux
            def update_progress(percent, message):
                progress.setValue(percent)
                progress.setLabelText(f"{message}\n\n{percent}%")
            
            def download_finished(success, message):
                download_result['success'] = success
                download_result['message'] = message
                progress.close()
                event_loop.quit()  # Sortir de la boucle d'attente
            
            downloader.progress_updated.connect(update_progress)
            downloader.download_finished.connect(download_finished)
            
            # Démarrer le téléchargement
            downloader.start()
            
            # Attendre la fin dans une boucle d'événements (non bloquante pour les signaux)
            event_loop.exec_()
            
            # Vérifier le résultat
            if not download_result['success']:
                QMessageBox.critical(
                    None,
                    "Download Failed / Échec",
                    f"Failed to download database:\n{download_result['message']}\n\n"
                    f"Échec du téléchargement:\n{download_result['message']}"
                )
                return
            
            if not db.is_installed():
                QMessageBox.critical(
                    None,
                    "Error / Erreur",
                    "Database installation failed. Please try again.\n\n"
                    "L'installation de la base de données a échoué. Veuillez réessayer."
                )
                return
        else:
            # BDD existe - Vérifier l'âge
            stats = db.get_statistics()
            age_days = stats['age_days']
            
            # N'afficher le dialogue que si la BDD a plus de 90 jours
            if age_days is not None and age_days > 90:
                emoji, status_label = db.get_status_emoji()
                
                age_text = f"{age_days} days / jours"
                
                msg = QMessageBox()
                msg.setWindowTitle("Taxonomy Database Status / Statut BDD Taxonomique")
                msg.setTextFormat(Qt.RichText)
                msg.setIcon(QMessageBox.Information)
                
                status_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 10pt;">
<h3>{emoji} Database Status / Statut: {status_label}</h3>
<table>
<tr><td><b>Version:</b></td><td>{stats['version'] or 'Unknown / Inconnue'}</td></tr>
<tr><td><b>Installed / Installée:</b></td><td>{stats['install_date'] or 'Unknown / Inconnue'}</td></tr>
<tr><td><b>Age / Âge:</b></td><td>{age_text}</td></tr>
<tr><td><b>Total Taxa / Taxons:</b></td><td>{stats['total_taxa']:,}</td></tr>
<tr><td><b>Size / Taille:</b></td><td>{stats['size_mb']} MB</td></tr>
</table>
</div>
"""
                msg.setText(status_html)
                
                refresh_btn = msg.addButton("Refresh / Rafraîchir", QMessageBox.ActionRole)
                continue_btn = msg.addButton("Continue Without Refresh / Continuer Sans Rafraîchir", QMessageBox.AcceptRole)
                msg.setDefaultButton(continue_btn)
                
                msg.exec_()
                
                if msg.clickedButton() == refresh_btn:
                    # Rafraîchissement
                    downloader = DatabaseDownloader(plugin_dir, self.iface.mainWindow())
                    
                    # Créer une boucle d'événements
                    from qgis.PyQt.QtCore import QEventLoop
                    refresh_loop = QEventLoop()
                    
                    progress = QProgressDialog(
                        "Refreshing taxonomy database...\nRafraîchissement de la base taxonomique...",
                        None,
                        0,
                        100,
                        self.iface.mainWindow()
                    )
                    progress.setWindowTitle("Database Refresh / Rafraîchissement BDD")
                    progress.setWindowModality(Qt.WindowModal)
                    progress.setMinimumDuration(0)
                    progress.setCancelButton(None)
                    progress.show()
                    
                    # Variable pour le résultat
                    refresh_result = {'success': False, 'message': ''}
                    
                    def update_progress_refresh(percent, message):
                        progress.setValue(percent)
                        progress.setLabelText(f"{message}\n\n{percent}%")
                    
                    def refresh_finished(success, message):
                        refresh_result['success'] = success
                        refresh_result['message'] = message
                        progress.close()
                        refresh_loop.quit()
                    
                    downloader.progress_updated.connect(update_progress_refresh)
                    downloader.download_finished.connect(refresh_finished)
                    
                    downloader.start()
                    
                    # Attendre la fin
                    refresh_loop.exec_()
                    
                    # Afficher erreur si échec (mais continuer)
                    if not refresh_result['success']:
                        QMessageBox.warning(
                            None,
                            "Refresh Failed / Échec",
                            f"Failed to refresh database:\n{refresh_result['message']}\n\n"
                            f"Échec du rafraîchissement:\n{refresh_result['message']}\n\n"
                            "Continuing with current database / Continuation avec la base actuelle"
                        )
            # Sinon (BDD < 90 jours), continuer silencieusement sans afficher de dialogue
        
        # =========================================================
        # POINT 2 : Mémorisation du SCU en cours
        # =========================================================
        project = QgsProject.instance()
        self.scu_origine = project.crs()
        
        # =========================================================
        # POINT 3 : Appel du sous-programme "Cercle"
        # =========================================================
        cercle_tool = YD_Cercle(self.iface)
        
        # Connexion du signal de fin
        cercle_tool.finished.connect(self._on_cercle_finished)
        
        # Lancement
        cercle_tool.run()
    
    def _on_cercle_finished(self, lat, lon, rayon, layer_name):
        """
        Callback appelé à la fin du sous-programme Cercle
        
        POINT 4 : Récupération des données du cercle
        """
        # =========================================================
        # POINT 4 : Récupération des valeurs retournées
        # =========================================================
        self.latitude_centre = lat
        self.longitude_centre = lon
        self.rayon_metres = rayon
        self.nom_couche_cercle = layer_name
        
        # Récupération du dossier du projet
        project = QgsProject.instance()
        project_file = project.fileName()
        
        if project_file:
            import os
            self.dossier_projet = os.path.dirname(project_file)
        else:
            # Ne devrait jamais arriver (vérifié dans yd_Cercle)
            QMessageBox.critical(
                None,
                "Erreur",
                "Le projet QGIS n'est pas enregistré."
            )
            return
        
        # =========================================================
        # POINT 5 : Passage en SCU 4326
        # =========================================================
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        project.setCrs(crs_4326)
        self.iface.mapCanvas().setDestinationCrs(crs_4326)
        self.iface.mapCanvas().refresh()
        
        # =========================================================
        # POINT 6 : Saisie des champs d'ENTRÉE
        # =========================================================
        if not self._saisir_filtres_entree():
            # Annulation par l'utilisateur
            return
        
        # =========================================================
        # POINT 7 : Saisie des champs de SORTIE
        # =========================================================
        if not self._saisir_champs_sortie():
            # Annulation par l'utilisateur
            return
        
        # === FIN ÉTAPE C (Points 1-7) ===
        
        # Message temporaire de validation
        # Message de développement - Désactivé en production
        # QMessageBox.information(
        #     None,
        #     "Étape C validée - Test",
        #     f"Points 1 à 7 terminés :\n\n"
        #     f"=== CERCLE ===\n"
        #     f"• Couche : {self.nom_couche_cercle}\n"
        #     f"• Centre : {self.latitude_centre:.6f}, {self.longitude_centre:.6f}\n"
        #     f"• Rayon : {self.rayon_metres:.0f} m\n"
        #     f"• Dossier : {self.dossier_projet}\n\n"
        #     f"=== FILTRES ENTRÉE ===\n"
        #     f"• User : {self.filter_user or 'Tous'}\n"
        #     f"• Taxon : {self.filter_taxon or 'Tous'}\n"
        #     f"• Date début : {self.filter_date_start or 'Toutes'}\n"
        #     f"• Date fin : {self.filter_date_end or 'Toutes'}\n"
        #     f"• Qualité : {self.filter_quality or 'Tous'}\n\n"
        #     f"=== CHAMPS SORTIE ===\n"
        #     f"• Nombre de champs : {len(self.selected_fields)}\n"
        #     f"• Champs : {', '.join(self.selected_fields)}"
        # )

    def _saisir_filtres_entree(self):
        """
        POINT 6 : Saisie des champs d'ENTRÉE par boîte de dialogue
        
        Modes de filtrage par dates :
        - Date exacte (1 date)
        - Période (date début + date fin)
        - Mois spécifique (mois sur toutes les années)
        
        Autres filtres :
        - Taxon (saisie texte, Tous par défaut)
        - iNat User (saisie texte, Tous par défaut)
        - Qualité (Combo, Tous par défaut)
        """
        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("iNaturalist Import – Input Filters / Filtres d'entrée")
        dlg.setFixedWidth(570)

        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        layout.addLayout(form)

        # ========================================
        # CHAMP : iNat User
        # ========================================
        le_user = QLineEdit()
        le_user.setPlaceholderText("All / Tous")
        form.addRow("iNat User / Utilisateur iNat :", le_user)

        # ========================================
        # CHAMP : Taxon (nom scientifique)
        # ========================================
        le_taxon = QLineEdit()
        le_taxon.setPlaceholderText("All / Tous")
        form.addRow("Taxon (scientific name / nom scientifique) :", le_taxon)

        # ========================================
        # DATES - SECTION AVEC RADIO BUTTONS
        # ========================================
        special_date = QDate(1900, 1, 1)
        current_date = QDate.currentDate()
        one_year_ago = current_date.addYears(-1)
        
        # Espacement
        spacer1 = QLabel("")
        spacer1.setFixedHeight(20)
        form.addRow("", spacer1)
        
        # Radio buttons pour le mode de date
        from qgis.PyQt.QtWidgets import QRadioButton, QButtonGroup
        
        rb_period = QRadioButton("Period / Période (start date + end date)")
        rb_exact = QRadioButton("Exact date / Date exacte")
        rb_month = QRadioButton("Seasonality / Saisonnalité (all years / toutes années)")
        
        date_mode_group = QButtonGroup()
        date_mode_group.addButton(rb_period, 1)
        date_mode_group.addButton(rb_exact, 2)
        date_mode_group.addButton(rb_month, 3)
        
        rb_period.setChecked(True)  # Par défaut : Période
        
        radio_layout = QVBoxLayout()
        radio_layout.addWidget(rb_period)
        radio_layout.addWidget(rb_exact)
        radio_layout.addWidget(rb_month)
        radio_widget = QWidget()
        radio_widget.setLayout(radio_layout)
        
        form.addRow("Date filter mode / Mode filtrage dates :", radio_widget)
        
        # ========================================
        # WIDGETS POUR PÉRIODE (date début + fin)
        # ========================================
        
        # Date Début
        le_date_start_display = QLineEdit()
        le_date_start_display.setText("All / Toutes")
        le_date_start_display.setReadOnly(True)
        le_date_start_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
        
        le_date_start = QDateEdit()
        le_date_start.setMinimumDate(special_date)
        le_date_start.setMaximumDate(current_date)
        le_date_start.setDisplayFormat("yyyy-MM-dd")
        le_date_start.setDate(special_date)
        le_date_start.setVisible(False)
        
        def sync_date_start_display():
            if le_date_start.date() == special_date:
                le_date_start_display.setText("All / Toutes")
                le_date_start_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
            else:
                le_date_start_display.setText(le_date_start.date().toString("yyyy-MM-dd"))
                le_date_start_display.setStyleSheet("background-color: white; color: black;")
        
        le_date_start.dateChanged.connect(sync_date_start_display)
        
        start_container = QHBoxLayout()
        start_container.setSpacing(5)
        start_container.setContentsMargins(0, 0, 0, 0)
        start_container.addWidget(le_date_start_display)
        btn_cal_start = QPushButton("📅")
        btn_cal_start.setFixedWidth(40)
        btn_cal_start.setToolTip("Open calendar / Ouvrir le calendrier")
        start_container.addWidget(btn_cal_start)
        start_container.addWidget(le_date_start)
        start_widget = QWidget()
        start_widget.setLayout(start_container)
        
        start_label = QLabel("Start Date / Date de début :")
        form.addRow(start_label, start_widget)
        
        # Date Fin
        le_date_end_display = QLineEdit()
        le_date_end_display.setText("All / Toutes")
        le_date_end_display.setReadOnly(True)
        le_date_end_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
        
        le_date_end = QDateEdit()
        le_date_end.setMinimumDate(special_date)
        le_date_end.setMaximumDate(current_date)
        le_date_end.setDisplayFormat("yyyy-MM-dd")
        le_date_end.setDate(special_date)
        le_date_end.setVisible(False)
        
        def sync_date_end_display():
            if le_date_end.date() == special_date:
                le_date_end_display.setText("All / Toutes")
                le_date_end_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
            else:
                le_date_end_display.setText(le_date_end.date().toString("yyyy-MM-dd"))
                le_date_end_display.setStyleSheet("background-color: white; color: black;")
        
        le_date_end.dateChanged.connect(sync_date_end_display)
        
        end_container = QHBoxLayout()
        end_container.setSpacing(5)
        end_container.setContentsMargins(0, 0, 0, 0)
        end_container.addWidget(le_date_end_display)
        btn_cal_end = QPushButton("📅")
        btn_cal_end.setFixedWidth(40)
        btn_cal_end.setToolTip("Open calendar / Ouvrir le calendrier")
        end_container.addWidget(btn_cal_end)
        end_container.addWidget(le_date_end)
        end_widget = QWidget()
        end_widget.setLayout(end_container)
        
        end_label = QLabel("End Date / Date de fin :")
        form.addRow(end_label, end_widget)
        
        # ========================================
        # WIDGETS POUR DATE EXACTE
        # ========================================
        
        le_date_exact_display = QLineEdit()
        le_date_exact_display.setText("All / Toutes")
        le_date_exact_display.setReadOnly(True)
        le_date_exact_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
        
        le_date_exact = QDateEdit()
        le_date_exact.setMinimumDate(special_date)
        le_date_exact.setMaximumDate(current_date)
        le_date_exact.setDisplayFormat("yyyy-MM-dd")
        le_date_exact.setDate(special_date)
        le_date_exact.setVisible(False)
        
        def sync_date_exact_display():
            if le_date_exact.date() == special_date:
                le_date_exact_display.setText("All / Toutes")
                le_date_exact_display.setStyleSheet("background-color: white; color: gray; font-style: italic;")
            else:
                le_date_exact_display.setText(le_date_exact.date().toString("yyyy-MM-dd"))
                le_date_exact_display.setStyleSheet("background-color: white; color: black;")
        
        le_date_exact.dateChanged.connect(sync_date_exact_display)
        
        exact_container = QHBoxLayout()
        exact_container.setSpacing(5)
        exact_container.setContentsMargins(0, 0, 0, 0)
        exact_container.addWidget(le_date_exact_display)
        btn_cal_exact = QPushButton("📅")
        btn_cal_exact.setFixedWidth(40)
        btn_cal_exact.setToolTip("Open calendar / Ouvrir le calendrier")
        exact_container.addWidget(btn_cal_exact)
        exact_container.addWidget(le_date_exact)
        exact_widget = QWidget()
        exact_widget.setLayout(exact_container)
        exact_widget.setVisible(False)  # Caché par défaut
        
        exact_label = QLabel("Exact Date / Date exacte :")
        exact_label.setVisible(False)  # Caché par défaut
        form.addRow(exact_label, exact_widget)
        
        # ========================================
        # WIDGETS POUR MOIS (CHECKBOXES)
        # ========================================
        
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # Conteneur principal pour les mois
        month_main_widget = QWidget()
        month_main_layout = QVBoxLayout()
        month_main_layout.setContentsMargins(0, 0, 0, 0)
        month_main_layout.setSpacing(5)
        
        # Boutons Tous / Aucun
        month_buttons_layout = QHBoxLayout()
        btn_all_months = QPushButton("✓ All / Tous")
        btn_no_months = QPushButton("✗ None / Aucun")
        btn_all_months.setMaximumWidth(120)
        btn_no_months.setMaximumWidth(120)
        month_buttons_layout.addWidget(btn_all_months)
        month_buttons_layout.addWidget(btn_no_months)
        month_buttons_layout.addStretch()
        month_main_layout.addLayout(month_buttons_layout)
        
        # Grille de checkboxes (3 colonnes x 4 lignes - notion de trimestres)
        month_grid = QGridLayout()
        month_grid.setSpacing(5)
        month_checkboxes = []
        
        for i, month_abbr in enumerate(month_names):
            checkbox = QCheckBox(month_abbr)
            checkbox.setChecked(True)  # Tous cochés par défaut
            month_checkboxes.append(checkbox)
            row = i // 3  # 3 colonnes
            col = i % 3
            month_grid.addWidget(checkbox, row, col)
        
        month_main_layout.addLayout(month_grid)
        month_main_widget.setLayout(month_main_layout)
        month_main_widget.setVisible(False)  # Caché par défaut
        
        # Fonctions pour boutons Tous/Aucun
        def select_all_months():
            for cb in month_checkboxes:
                cb.setChecked(True)
        
        def select_no_months():
            for cb in month_checkboxes:
                cb.setChecked(False)
        
        btn_all_months.clicked.connect(select_all_months)
        btn_no_months.clicked.connect(select_no_months)
        
        month_label = QLabel("Seasonality / Saisonnalité :")
        month_label.setVisible(False)  # Caché par défaut
        form.addRow(month_label, month_main_widget)
        
        # ========================================
        # BOUTON RESET DATES (créé ici pour être accessible dans update_date_mode)
        # ========================================
        
        def reset_dates():
            """Réinitialise toutes les dates à All / Toutes"""
            le_date_start.setDate(special_date)
            le_date_end.setDate(special_date)
            le_date_exact.setDate(special_date)
            # Cocher tous les mois
            for cb in month_checkboxes:
                cb.setChecked(True)
        
        btn_reset_dates = QPushButton("⟲ Reset to All / Toutes")
        btn_reset_dates.setToolTip("Reset all dates to All / Réinitialiser toutes les dates à Toutes")
        btn_reset_dates.clicked.connect(reset_dates)
        form.addRow("", btn_reset_dates)
        
        # ========================================
        # FONCTION : Changer mode de date
        # ========================================
        
        def update_date_mode():
            """Affiche/cache les widgets ET les labels selon le mode sélectionné"""
            mode = date_mode_group.checkedId()
            
            if mode == 1:  # Période
                start_label.setVisible(True)
                start_widget.setVisible(True)
                end_label.setVisible(True)
                end_widget.setVisible(True)
                exact_label.setVisible(False)
                exact_widget.setVisible(False)
                month_label.setVisible(False)
                month_main_widget.setVisible(False)
                btn_reset_dates.setVisible(True)  # Bouton reset visible
            elif mode == 2:  # Date exacte
                start_label.setVisible(False)
                start_widget.setVisible(False)
                end_label.setVisible(False)
                end_widget.setVisible(False)
                exact_label.setVisible(True)
                exact_widget.setVisible(True)
                month_label.setVisible(False)
                month_main_widget.setVisible(False)
                btn_reset_dates.setVisible(True)  # Bouton reset visible
            elif mode == 3:  # Mois
                start_label.setVisible(False)
                start_widget.setVisible(False)
                end_label.setVisible(False)
                end_widget.setVisible(False)
                exact_label.setVisible(False)
                exact_widget.setVisible(False)
                month_label.setVisible(True)
                month_main_widget.setVisible(True)
                btn_reset_dates.setVisible(False)  # Bouton reset caché en mode mois
        
        rb_period.toggled.connect(update_date_mode)
        rb_exact.toggled.connect(update_date_mode)
        rb_month.toggled.connect(update_date_mode)
        
        # ========================================
        # VALIDATION DES DATES
        # ========================================
        
        def validate_dates():
            """Valide la cohérence des dates selon le mode - APPELÉ SEULEMENT AU CLIC OK"""
            mode = date_mode_group.checkedId()
            
            if mode == 1:  # Période
                date_start = le_date_start.date()
                date_end = le_date_end.date()
                
                # Cas 1 : Les deux à "All" → OK
                if date_start == special_date and date_end == special_date:
                    return True
                
                # Cas 2 : Une seule date précise → ERREUR
                if ((date_start == special_date and date_end != special_date) or
                    (date_start != special_date and date_end == special_date)):
                    return False
                
                # Cas 3 : Deux dates précises
                if date_start != special_date and date_end != special_date:
                    # Fin <= Début → ERREUR
                    if date_end <= date_start:
                        return False
                    else:
                        return True
            
            # Autres modes : toujours valide
            return True
        
        # NE PLUS connecter la validation automatique
        # La validation se fait uniquement au clic sur OK
        # le_date_start.dateChanged.connect(validate_dates)
        # le_date_end.dateChanged.connect(validate_dates)
        
        # ========================================
        # POPUPS CALENDRIER
        # ========================================
        
        def show_calendar_start():
            popup = QDialog(dlg)
            popup.setWindowTitle("Select Start Date / Sélectionner Date Début")
            popup.setModal(True)
            popup_layout = QVBoxLayout()
            
            cal = QCalendarWidget()
            if le_date_start.date() != special_date:
                cal.setSelectedDate(le_date_start.date())
            else:
                cal.setSelectedDate(one_year_ago)
            popup_layout.addWidget(cal)
            
            btn_layout = QHBoxLayout()
            btn_ok_cal = QPushButton("OK")
            btn_all = QPushButton("All / Toutes")
            btn_layout.addWidget(btn_ok_cal)
            btn_layout.addWidget(btn_all)
            popup_layout.addLayout(btn_layout)
            
            def set_date():
                le_date_start.setDate(cal.selectedDate())
                popup.accept()
            
            def set_all():
                le_date_start.setDate(special_date)
                popup.accept()
            
            btn_ok_cal.clicked.connect(set_date)
            btn_all.clicked.connect(set_all)
            
            popup.setLayout(popup_layout)
            popup.exec_()
        
        def show_calendar_end():
            popup = QDialog(dlg)
            popup.setWindowTitle("Select End Date / Sélectionner Date Fin")
            popup.setModal(True)
            popup_layout = QVBoxLayout()
            
            cal = QCalendarWidget()
            if le_date_end.date() != special_date:
                cal.setSelectedDate(le_date_end.date())
            else:
                cal.setSelectedDate(current_date)
            popup_layout.addWidget(cal)
            
            btn_layout = QHBoxLayout()
            btn_ok_cal = QPushButton("OK")
            btn_all = QPushButton("All / Toutes")
            btn_layout.addWidget(btn_ok_cal)
            btn_layout.addWidget(btn_all)
            popup_layout.addLayout(btn_layout)
            
            def set_date():
                le_date_end.setDate(cal.selectedDate())
                popup.accept()
            
            def set_all():
                le_date_end.setDate(special_date)
                popup.accept()
            
            btn_ok_cal.clicked.connect(set_date)
            btn_all.clicked.connect(set_all)
            
            popup.setLayout(popup_layout)
            popup.exec_()
        
        def show_calendar_exact():
            popup = QDialog(dlg)
            popup.setWindowTitle("Select Exact Date / Sélectionner Date Exacte")
            popup.setModal(True)
            popup_layout = QVBoxLayout()
            
            cal = QCalendarWidget()
            if le_date_exact.date() != special_date:
                cal.setSelectedDate(le_date_exact.date())
            else:
                cal.setSelectedDate(current_date)
            popup_layout.addWidget(cal)
            
            btn_layout = QHBoxLayout()
            btn_ok_cal = QPushButton("OK")
            btn_all = QPushButton("All / Toutes")
            btn_layout.addWidget(btn_ok_cal)
            btn_layout.addWidget(btn_all)
            popup_layout.addLayout(btn_layout)
            
            def set_date():
                le_date_exact.setDate(cal.selectedDate())
                popup.accept()
            
            def set_all():
                le_date_exact.setDate(special_date)
                popup.accept()
            
            btn_ok_cal.clicked.connect(set_date)
            btn_all.clicked.connect(set_all)
            
            popup.setLayout(popup_layout)
            popup.exec_()
        
        btn_cal_start.clicked.connect(show_calendar_start)
        btn_cal_end.clicked.connect(show_calendar_end)
        btn_cal_exact.clicked.connect(show_calendar_exact)
        
        # Espacement
        spacer2 = QLabel("")
        spacer2.setFixedHeight(20)
        form.addRow("", spacer2)

        # ========================================
        # CHAMP : Qualité
        # ========================================
        cb_quality = QComboBox()
        cb_quality.addItems(["All / Tous", "research", "casual", "needs_id"])
        form.addRow("Quality / Qualité :", cb_quality)

        layout.addSpacing(20)

        # ========================================
        # BOUTON OK avec validation
        # ========================================
        btn_ok = QPushButton("OK")
        btn_ok.setFixedHeight(35)
        
        def try_accept():
            """Tente de valider et fermer le dialogue"""
            mode = date_mode_group.checkedId()
            
            if validate_dates():
                dlg.accept()
            else:
                # Construire le message d'erreur selon le cas
                if mode == 1:  # Période
                    date_start = le_date_start.date()
                    date_end = le_date_end.date()
                    
                    # Déterminer le type d'erreur
                    if ((date_start == special_date and date_end != special_date) or
                        (date_start != special_date and date_end == special_date)):
                        error_msg = (
                            "⚠️ Error / Erreur:\n\n"
                            "Both dates must be set or both set to 'All'.\n\n"
                            "Les deux dates doivent être définies ou toutes deux à 'All'."
                        )
                    elif date_end <= date_start:
                        error_msg = (
                            "⚠️ Error / Erreur:\n\n"
                            "End date must be after Start date.\n\n"
                            "La date de fin doit être après la date de début."
                        )
                    else:
                        error_msg = "Invalid dates / Dates invalides"
                    
                    QMessageBox.warning(
                        dlg,
                        "Invalid Dates / Dates Invalides",
                        error_msg
                    )
        
        btn_ok.clicked.connect(try_accept)
        layout.addWidget(btn_ok)
        
        # Donner le focus au bouton OK dès l'ouverture
        btn_ok.setFocus()

        if dlg.exec() != QDialog.Accepted:
            return False  # Annulation

        # ========================================
        # MÉMORISATION DES FILTRES SÉLECTIONNÉS
        # ========================================
        self.filter_user = le_user.text().strip() or None
        self.filter_taxon = le_taxon.text().strip() or None
        
        # Récupérer les dates selon le mode
        mode = date_mode_group.checkedId()
        
        if mode == 1:  # Période
            date_start = le_date_start.date()
            date_end = le_date_end.date()
            self.filter_date_start = date_start.toString("yyyy-MM-dd") if date_start != special_date else None
            self.filter_date_end = date_end.toString("yyyy-MM-dd") if date_end != special_date else None
            self.filter_month = None
            
        elif mode == 2:  # Date exacte
            date_exact = le_date_exact.date()
            if date_exact != special_date:
                # Même date pour début et fin
                self.filter_date_start = date_exact.toString("yyyy-MM-dd")
                self.filter_date_end = date_exact.toString("yyyy-MM-dd")
            else:
                self.filter_date_start = None
                self.filter_date_end = None
            self.filter_month = None
            
        elif mode == 3:  # Mois
            # Récupérer tous les mois cochés (1-12)
            selected_months = []
            for i, cb in enumerate(month_checkboxes):
                if cb.isChecked():
                    selected_months.append(i + 1)  # Janvier = 1, etc.
            
            # Stocker la liste des mois (ou None si aucun mois sélectionné)
            self.filter_month = selected_months if selected_months else None
            self.filter_date_start = None
            self.filter_date_end = None
        
        quality_text = cb_quality.currentText()
        self.filter_quality = None if quality_text == "All / Tous" else quality_text
        
        return True  # Validation OK

    def _saisir_champs_sortie(self):
        """
        POINT 7 : Saisie des champs de SORTIE par boîte de dialogue
        
        Permet de sélectionner les champs optionnels à inclure dans la table principale.
        Les champs obligatoires (inat_id, taxon_id) sont toujours inclus.
        """
        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("iNaturalist Import – Output Fields / Champs de sortie")
        dlg.setFixedWidth(550)

        layout = QVBoxLayout(dlg)
        
        # Titre / Instructions
        label_info = QLabel(
            "Select the fields to include in the output layer:\n"
            "Sélectionnez les champs à inclure dans la couche de sortie :"
        )
        label_info.setWordWrap(True)
        label_info.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(label_info)
        
        layout.addSpacing(10)
        
        # ========================================
        # DÉFINITION DES CHAMPS
        # ========================================
        # Liste complète des champs dans l'ordre
        # Les champs obligatoires ne sont PAS affichés dans la sélection
        all_fields = [
            ("inat_id", "iNaturalist ID", True),           # Obligatoire (*)
            ("date_obs", "Observation Date / Date", False),
            ("scientific_name", "Scientific Name / Nom scientifique", False),
            ("vernacular_name_FR", "Common Name (FR) / Nom vernaculaire", False),
            ("latitude", "Latitude", False),
            ("longitude", "Longitude", False),
            ("place_guess", "Location / Lieu", False),
            ("taxon_id", "Taxon ID", True),                # Obligatoire (*)
            ("taxon_rank", "Taxonomic Rank / Rang taxonomique", False),
            ("url_obs", "Observation URL / URL observation", False),
            ("url_taxon", "Taxon URL / URL taxon", False),
            ("observateur_id", "Observer ID / ID observateur", False),
            ("observateur_name", "Observer Name / Nom observateur", False),
            ("quality_grade", "Quality Grade / Qualité", False),
            ("precision", "Precision (m) / Précision", False),
            ("nbr_photos", "Number of Photos / Nombre de photos", False),
        ]
        
        # Filtrer uniquement les champs optionnels pour l'affichage
        optional_fields = [(name, label) for name, label, mandatory in all_fields if not mandatory]
        
        # ========================================
        # GRILLE DE CASES À COCHER (2 COLONNES)
        # ========================================
        grid = QGridLayout()
        grid.setSpacing(8)
        
        self.field_checkboxes = {}
        
        # Calcul du nombre de lignes nécessaires
        num_fields = len(optional_fields)
        num_rows = (num_fields + 1) // 2  # Arrondi supérieur
        
        for idx, (field_name, field_label) in enumerate(optional_fields):
            checkbox = QCheckBox(field_label)
            checkbox.setChecked(True)  # Tous cochés par défaut
            self.field_checkboxes[field_name] = checkbox
            
            # Placement sur 2 colonnes
            row = idx % num_rows
            col = idx // num_rows
            grid.addWidget(checkbox, row, col)
        
        layout.addLayout(grid)
        
        layout.addSpacing(15)
        
        # ========================================
        # BOUTONS DE SÉLECTION RAPIDE
        # ========================================
        btn_layout = QHBoxLayout()
        
        btn_select_all = QPushButton("✓ Select All / Tout sélectionner")
        btn_select_all.setToolTip("Check all optional fields / Cocher tous les champs optionnels")
        
        btn_select_none = QPushButton("✗ Select None / Ne rien sélectionner")
        btn_select_none.setToolTip("Uncheck all optional fields / Décocher tous les champs optionnels")
        
        def select_all():
            for checkbox in self.field_checkboxes.values():
                checkbox.setChecked(True)
        
        def select_none():
            for checkbox in self.field_checkboxes.values():
                checkbox.setChecked(False)
        
        btn_select_all.clicked.connect(select_all)
        btn_select_none.clicked.connect(select_none)
        
        btn_layout.addWidget(btn_select_all)
        btn_layout.addWidget(btn_select_none)
        
        layout.addLayout(btn_layout)
        
        layout.addSpacing(20)
        
        # ========================================
        # BOUTON OK
        # ========================================
        btn_ok = QPushButton("OK")
        btn_ok.setFixedHeight(35)
        btn_ok.clicked.connect(dlg.accept)
        layout.addWidget(btn_ok)
        
        # Donner le focus au bouton OK dès l'ouverture
        btn_ok.setFocus()

        if dlg.exec() != QDialog.Accepted:
            return False  # Annulation

        # ========================================
        # MÉMORISATION DES CHAMPS SÉLECTIONNÉS
        # ========================================
        # On construit la liste ordonnée finale en respectant l'ordre de all_fields
        self.selected_fields = []
        
        for field_name, field_label, mandatory in all_fields:
            if mandatory:
                # Champs obligatoires : toujours inclus
                self.selected_fields.append(field_name)
            else:
                # Champs optionnels : selon sélection utilisateur
                if self.field_checkboxes[field_name].isChecked():
                    self.selected_fields.append(field_name)
        
        # Vérification : au moins les 2 champs obligatoires
        if len(self.selected_fields) < 2:
            QMessageBox.warning(
                None,
                "Warning / Attention",
                "At least the mandatory fields must be included.\n"
                "Au moins les champs obligatoires doivent être inclus."
            )
            return False
        
        # =========================================================
        # POINT 8 : Lancement de la récupération des données
        # =========================================================
        self._run_point_8()
        
        return True  # Validation OK
    
    # =================================================================
    # POINT 8 : TRAITEMENT PRINCIPAL (Requête API iNaturalist)
    # =================================================================
    
    def _run_point_8(self):
        """
        Lance la tâche asynchrone de récupération des observations
        iNaturalist via l'API avec tous les filtres appliqués
        """
        import os
        from qgis.PyQt.QtGui import QMovie
        from qgis.core import QgsApplication, QgsTask
        from PyQt5.QtCore import pyqtSignal
        import re
        from .yd_iNat_Core import run_inat_query, count_inat_observations
        
        # =========================================================
        # AFFICHAGE DU DIALOGUE D'ATTENTE AVEC BARRE DE PROGRESSION
        # =========================================================
        
        plugin_dir = os.path.dirname(__file__)
        
        self.info_dialog = QDialog(self.iface.mainWindow())
        self.info_dialog.setWindowTitle("iNaturalist Import")
        self.info_dialog.setModal(False)
        self.info_dialog.setFixedSize(500, 200)
        layout = QVBoxLayout(self.info_dialog)
        
        # Titre
        title_label = QLabel("<h3>Downloading observations from iNaturalist API</h3>"
                            "<h3>Téléchargement des observations depuis l'API iNaturalist</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v / %m observations")
        layout.addWidget(self.progress_bar)
        
        # Label de statut
        self.status_label = QLabel("Preparing download...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # NE PAS afficher le dialogue maintenant
        # Il sera affiché seulement après le comptage si l'utilisateur continue
        
        # =========================================================
        # CLASSE DE TÂCHE ASYNCHRONE Step8Task
        # =========================================================
        
        class Step8Task(QgsTask):
            """
            Tâche asynchrone pour récupérer les observations iNaturalist
            avec application de tous les filtres côté serveur
            """
            
            taskCompleted = pyqtSignal(list, list, dict)  # (observations, photos, metadata)
            progressUpdated = pyqtSignal(int, int, str)  # (current, total, message)
            
            def __init__(self, lat, lng, radius_km, date_start, date_end, 
                         user, taxon, quality, month=None):
                super().__init__(
                    "iNaturalist Import - API Query",
                    QgsTask.CanCancel
                )
                self.lat = lat
                self.lng = lng
                self.radius_km = radius_km
                self.date_start = date_start
                self.date_end = date_end
                self.user = user
                self.taxon = taxon
                self.quality = quality
                self.month = month  # Mois spécifique (1-12) ou None
                self.observations = []
                self.photos = []
                self.metadata = {}  # Métadonnées de l'import
            
            def progress_callback(self, current, total, message):
                """Callback pour la progression"""
                self.progressUpdated.emit(current, total, message)
                
            def run(self):
                """
                Exécution de la requête API avec tous les filtres
                """
                try:
                    # Appel à l'API avec TOUS les filtres
                    result = run_inat_query(
                        lat=self.lat,
                        lng=self.lng,
                        radius_km=self.radius_km,
                        d1=self.date_start,
                        d2=self.date_end,
                        month=self.month,
                        user_login=self.user,
                        taxon_name=self.taxon,
                        quality_grade=self.quality,
                        locale="fr",
                        diagnostic=False,
                        progress_callback=self.progress_callback
                    )
                    
                    # Extraire observations et métadonnées
                    self.observations = result['observations']
                    self.metadata = result['metadata']
                    
                    # Extraction des photos avec conversion en format 'original'
                    for obs in self.observations:
                        obs_photos = obs.get("observation_photos", [])
                        
                        # Calculer le nombre de photos pour chaque observation
                        obs["_nbr_photos"] = len(obs_photos)
                        
                        # Traitement des URLs de photos
                        for idx, obs_photo in enumerate(obs_photos, start=1):
                            photo = obs_photo.get("photo", {})
                            url = photo.get("url", "")
                            
                            if url:
                                # Conversion en résolution 'original' avec regex robuste
                                url = re.sub(
                                    r'/(square|small|medium|large)\.(jpg|jpeg|png|gif)',
                                    r'/original.\2',
                                    url,
                                    flags=re.IGNORECASE
                                )
                                # Cache-busting pour QGIS/Qt
                                url = f"{url}?inat_original=1"
                            
                            # Ajout à la liste des photos
                            self.photos.append({
                                "inat_id": obs.get("id"),
                                "photo_rank": idx,
                                "photo_label": f"Photo{idx}",
                                "identifier": url
                            })
                    
                    return True
                    
                except Exception as e:
                    self.exception = e
                    return False
            
            def finished(self, result):
                """Appelé automatiquement à la fin de la tâche"""
                if result:
                    self.taskCompleted.emit(self.observations, self.photos, self.metadata)
        
        # =========================================================
        # LANCEMENT DE LA TÂCHE ASYNCHRONE
        # =========================================================
        
        # Préparation des filtres (convertir "All / Tous" en None)
        user_filter = None
        if self.filter_user and self.filter_user not in ("All / Tous", ""):
            user_filter = self.filter_user
        
        taxon_filter = None
        if self.filter_taxon and self.filter_taxon not in ("All / Tous", ""):
            taxon_filter = self.filter_taxon
        
        quality_filter = None
        if self.filter_quality and self.filter_quality not in ("All / Tous", ""):
            quality_filter = self.filter_quality
        
        # =========================================================
        # COMPTAGE PRÉALABLE DES OBSERVATIONS
        # =========================================================
        print(f"\n{'='*70}")
        print(f"📊 Comptage préalable des observations...")
        print(f"{'='*70}")
        
        total_count = count_inat_observations(
            lat=self.latitude_centre,
            lng=self.longitude_centre,
            radius_km=self.rayon_metres / 1000.0,
            d1=self.filter_date_start,
            d2=self.filter_date_end,
            month=self.filter_month,
            user_login=user_filter,
            taxon_name=taxon_filter,
            quality_grade=quality_filter,
            locale="fr"
        )
        
        if total_count is not None:
            print(f"✅ Total disponible : {total_count:,} observations")
            
            # Avertissement si > 10 000
            if total_count > 10000:
                from qgis.PyQt.QtWidgets import QMessageBox
                
                msg = QMessageBox()
                msg.setWindowTitle("High Observation Count / Nombre élevé d'observations")
                msg.setIcon(QMessageBox.Warning)
                msg.setTextFormat(Qt.RichText)
                
                # Calculer estimation import
                estimated_import = min(total_count, 10000)
                if estimated_import >= 10000:
                    estimated_import = "~9,500-9,900"  # Avec le stop propre
                
                warning_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 10pt;">
<h3>⚠️ Very Large Query - Server Load Warning</h3>
<p><b>Your query returns: {total_count:,} observations</b></p>

<p style="color: #d9534f; font-weight: bold;">
⚠️ This represents a significant load on iNaturalist's free public servers.
</p>

<p>The iNaturalist API is a <b>free community resource</b> maintained by a non-profit organization.
Large queries like this one consume substantial server resources and bandwidth that could serve
hundreds of other users.</p>

<p><b>Please consider refining your search criteria:</b></p>
<ul>
<li>Reduce the search area (smaller circle radius)</li>
<li>Add a date range filter (e.g., last year only)</li>
<li>Filter by taxon (family, genus, or species)</li>
<li>Filter by quality grade or observer</li>
</ul>

<p style="background-color: #fff3cd; padding: 8px; border-left: 3px solid #f0ad4e;">
<b>⚡ API Limit:</b> Maximum 10,000 observations per query<br>
<b>📅 Import Strategy:</b> Most recent to oldest (by observation date)<br>
<b>🛑 Clean Stop:</b> Last complete date to ensure data integrity<br>
<b>📊 Estimated Import:</b> <b>{estimated_import}</b> observations
</p>

<hr>

<h3>⚠️ Requête très volumineuse - Charge serveur</h3>
<p><b>Votre requête retourne : {total_count:,} observations</b></p>

<p style="color: #d9534f; font-weight: bold;">
⚠️ Cela représente une charge importante sur les serveurs publics gratuits d'iNaturalist.
</p>

<p>L'API iNaturalist est une <b>ressource communautaire gratuite</b> maintenue par une organisation
à but non lucratif. Les requêtes volumineuses comme celle-ci consomment des ressources serveur et
de la bande passante considérables qui pourraient servir des centaines d'autres utilisateurs.</p>

<p><b>Merci d'envisager d'affiner vos critères de recherche :</b></p>
<ul>
<li>Réduire la zone de recherche (rayon de cercle plus petit)</li>
<li>Ajouter un filtre de dates (ex: dernière année seulement)</li>
<li>Filtrer par taxon (famille, genre ou espèce)</li>
<li>Filtrer par qualité ou observateur</li>
</ul>

<p style="background-color: #fff3cd; padding: 8px; border-left: 3px solid #f0ad4e;">
<b>⚡ Limite API :</b> Maximum 10 000 observations par requête<br>
<b>📅 Stratégie d'import :</b> Du plus récent au plus ancien (par date d'observation)<br>
<b>🛑 Arrêt propre :</b> Dernière date complète pour garantir l'intégrité<br>
<b>📊 Import estimé :</b> <b>{estimated_import}</b> observations
</p>
</div>
"""
                msg.setText(warning_html)
                
                continue_btn = msg.addButton("Continue Anyway / Continuer quand même", QMessageBox.AcceptRole)
                stop_btn = msg.addButton("Stop Program / Arrêter le programme", QMessageBox.RejectRole)
                msg.setDefaultButton(stop_btn)
                
                msg.exec_()
                
                if msg.clickedButton() == stop_btn:
                    print("❌ Import annulé par l'utilisateur - arrêt du programme")
                    
                    # Fermer définitivement le dialogue d'attente
                    if hasattr(self, 'info_dialog') and self.info_dialog:
                        self.info_dialog.close()
                        self.info_dialog = None
                    
                    # Supprimer la couche cercle
                    project = QgsProject.instance()
                    layers_to_remove = []
                    
                    for layer in project.mapLayers().values():
                        if layer.name() == self.nom_couche_cercle:
                            layers_to_remove.append(layer.id())
                            print(f"🗑️  Suppression de la couche : {layer.name()}")
                    
                    if layers_to_remove:
                        project.removeMapLayers(layers_to_remove)
                    
                    # Arrêter proprement le script
                    QMessageBox.information(
                        self.iface.mainWindow(),
                        "Program Stopped / Programme arrêté",
                        "The import has been cancelled.\n"
                        "Please refine your search criteria (smaller area, date range, taxon filter, etc.)\n\n"
                        "L'import a été annulé.\n"
                        "Veuillez affiner vos critères de recherche (zone plus petite, période de dates, filtre taxon, etc.)"
                    )
                    return  # Sortie du script
                
                print("▶️ Utilisateur a choisi de continuer malgré l'avertissement")
        else:
            print("⚠️ Impossible de compter les observations (continuons quand même)")
        
        # Afficher le dialogue d'attente MAINTENANT (après le comptage)
        if hasattr(self, 'info_dialog') and self.info_dialog:
            self.info_dialog.show()
            self.info_dialog.raise_()
            QApplication.processEvents()
        
        # Création et lancement de la tâche
        self.task_step8 = Step8Task(
            lat=self.latitude_centre,
            lng=self.longitude_centre,
            radius_km=self.rayon_metres / 1000.0,  # Conversion m → km
            date_start=self.filter_date_start,
            date_end=self.filter_date_end,
            user=user_filter,
            taxon=taxon_filter,
            quality=quality_filter,
            month=self.filter_month
        )
        
        # Connexion des signaux
        self.task_step8.taskCompleted.connect(self._on_point_8_finished)
        self.task_step8.progressUpdated.connect(self._on_progress_updated)
        
        # Ajout au gestionnaire de tâches QGIS
        QgsApplication.taskManager().addTask(self.task_step8)
    
    def _on_progress_updated(self, current, total, message):
        """
        Callback appelé pendant le téléchargement pour mettre à jour la progression
        
        Paramètres:
            current (int): Nombre d'observations téléchargées
            total (int): Nombre total d'observations à télécharger
            message (str): Message de statut
        """
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.setText(f"{message}\n{current:,} / {total:,} observations")
        
        QApplication.processEvents()
    
    def _on_point_8_finished(self, observations, photos, metadata):
        """
        Callback appelé à la fin de la récupération des données
        
        Paramètres:
            observations (list): Liste des observations récupérées
            photos (list): Liste des photos associées
            metadata (dict): Métadonnées de l'import (total, limite, etc.)
        """
        # Fermeture du dialogue d'attente
        if hasattr(self, 'info_dialog') and self.info_dialog:
            self.info_dialog.close()
            self.info_dialog = None
        
        # Mémorisation des résultats
        self.observations = observations
        self.photos = photos
        self.import_metadata = metadata  # Stocker les métadonnées
        
        # =========================================================
        # AFFICHAGE DES MÉTADONNÉES D'IMPORT
        # =========================================================
        print(f"\n{'='*70}")
        print(f"📊 MÉTADONNÉES D'IMPORT")
        print(f"{'='*70}")
        print(f"Total disponible    : {metadata.get('total_requested', 0):,} observations")
        print(f"Total importé       : {metadata.get('total_imported', 0):,} observations")
        print(f"Limite atteinte     : {'Oui (API iNaturalist limite à 10,000)' if metadata.get('limit_reached') else 'Non'}")
        
        if metadata.get('limit_reached'):
            print(f"📅 Dernière date complète : {metadata.get('last_complete_date', 'N/A')}")
            print(f"❌ Observations exclues   : {metadata.get('excluded_count', 0):,}")
            print(f"\n💡 Les observations du {metadata.get('last_complete_date', 'dernier jour')}")
            print(f"   et POSTÉRIEURES (plus récentes) ont été importées COMPLÈTEMENT.")
        
        print(f"{'='*70}\n")
        
        # Message de développement - Désactivé en production
        # QMessageBox.information(
        #     self.iface.mainWindow(),
        #     "iNaturalist Import - Point 8 Complete",
        #     f"✅ Data retrieval successful!\n\n"
        #     f"Number of observations: {len(observations)}\n"
        #     f"Number of photos: {len(photos)}\n\n"
        #     f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        #     f"✅ Récupération des données réussie !\n\n"
        #     f"Nombre d'observations : {len(observations)}\n"
        #     f"Nombre de photos : {len(photos)}"
        # )
        
        # =================================================================
        # PHASE 1 : Création GPKG et remplissage (approche robuste)
        # =================================================================
        self._run_phase_1()
    
    # =================================================================
    # PHASE 1 : CRÉATION GPKG ET REMPLISSAGE (APPROCHE ROBUSTE)
    # =================================================================
    
    def _run_phase_1(self):
        """
        PHASE 1 - Création directe en GPKG (approche ultra-robuste)
        
        Cette phase crée DIRECTEMENT un fichier GPKG contenant :
        - Couche principale : Points géolocalisés (EPSG:4326)
        - Table photos : Table attributaire sans géométrie
        
        POURQUOI CETTE APPROCHE ?
        -------------------------
        Les couches "memory" peuvent causer des crashs sur certaines
        configurations PC (notamment tables sans géométrie). En créant
        directement dans un GPKG, on assure un comportement identique
        sur TOUS les PC avec QGIS 3.40.
        
        WORKFLOW :
        ----------
        1. Créer un GPKG dans le dossier du projet
        2. Écrire la couche principale dans le GPKG
        3. Écrire la table photos dans le GPKG
        4. Charger les 2 couches depuis le GPKG
        5. Ajouter au projet QGIS
        
        AVANTAGES :
        -----------
        ✅ Aucun crash lié aux couches mémoire
        ✅ Comportement identique sur tous les PC
        ✅ Données déjà sauvegardées (sécurité)
        ✅ Pas de problème Qt/géométrie None
        
        À la fin de cette phase :
        - Le GPKG existe dans le dossier projet
        - Les 2 couches sont visibles dans QGIS
        - Les données sont complètes
        - AUCUNE relation n'est établie (Phase 3)
        - AUCUNE stylisation n'est appliquée (Phase 3)
        """
        from qgis.core import (
            QgsVectorLayer, QgsVectorFileWriter, QgsField, QgsFeature, 
            QgsGeometry, QgsPointXY, QgsFields, QgsCoordinateTransformContext
        )
        from qgis.PyQt.QtCore import QVariant
        import os
        
        project = QgsProject.instance()
        
        print(f"\n{'='*70}")
        print(f"PHASE 1 - Création GPKG et remplissage (approche robuste)")
        print(f"{'='*70}")
        
        # =============================================================
        # 1.1 - CONSTRUCTION DES NOMS ET CHEMINS
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.1 - Construction des noms et chemins")
        print(f"{'='*70}")
        
        # Nom de la couche principale : "iNat_(nom_cercle)_Ray=(rayon)m"
        rayon_arrondi = int(round(self.rayon_metres))
        self.nom_couche_principale = f"iNat_{self.nom_couche_cercle}_Ray={rayon_arrondi}m"
        self.nom_couche_photos = f"{self.nom_couche_principale}_Photos"
        
        # Chemin du GPKG dans le dossier projet
        if not self.dossier_projet:
            raise RuntimeError("Phase 1.1 - Dossier projet non défini")
        
        self.gpkg_path = os.path.join(
            self.dossier_projet,
            f"{self.nom_couche_principale}.gpkg"
        )
        
        print(f"Couche principale : {self.nom_couche_principale}")
        print(f"Table photos      : {self.nom_couche_photos}")
        print(f"Chemin GPKG       : {self.gpkg_path}")
        print(f"Observations      : {len(self.observations)}")
        print(f"Photos            : {len(self.photos)}")
        
        # Vérifier que le fichier n'existe pas déjà
        if os.path.exists(self.gpkg_path):
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                "File exists / Fichier existant",
                f"The file already exists:\n{self.gpkg_path}\n\n"
                f"Overwrite it?\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Le fichier existe déjà :\n{self.gpkg_path}\n\n"
                f"L'écraser ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                print("❌ Opération annulée par l'utilisateur")
                return
            else:
                os.remove(self.gpkg_path)
                print(f"🗑️  Fichier existant supprimé")
        
        # =============================================================
        # 1.2 - PRÉPARATION DES CHAMPS
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.2 - Préparation des champs")
        print(f"{'='*70}")
        
        # Ordre canonique des champs
        fields_order = [
            "inat_id", "date_obs", "scientific_name", "vernacular_name_FR",
            "latitude", "longitude", "place_guess", "taxon_id", "taxon_rank",
            "url_obs", "url_taxon", "observateur_id", "observateur_name",
            "quality_grade", "precision", "nbr_photos"
        ]
        
        # =============================================================
        # DÉFINITION DES TYPES DE CHAMPS
        # =============================================================
        # Mapping des noms de champs vers leurs types QVariant
        field_types = {
            # Champs Date
            "date_obs": QVariant.Date,
            
            # Champs Double (décimaux haute précision)
            "latitude": QVariant.Double,
            "longitude": QVariant.Double,
            
            # Champs Integer (entiers)
            "precision": QVariant.Int,
            "nbr_photos": QVariant.Int,
            
            # Tous les autres champs restent en String par défaut
        }
        
        # Création des champs selon sélection utilisateur
        fields_main = QgsFields()
        for field_name in fields_order:
            if field_name in self.selected_fields:
                # Utiliser le type spécifique ou String par défaut
                field_type = field_types.get(field_name, QVariant.String)
                fields_main.append(QgsField(field_name, field_type))
        
        print(f"✅ Champs couche principale : {len(fields_main)} champs")
        
        # Champs de la table photos (structure fixe)
        fields_photos = QgsFields()
        fields_photos.append(QgsField("inat_id", QVariant.String))
        fields_photos.append(QgsField("photo_rank", QVariant.Int))
        fields_photos.append(QgsField("photo_label", QVariant.String))
        fields_photos.append(QgsField("identifier", QVariant.String))
        
        print(f"✅ Champs table photos : {len(fields_photos)} champs")
        
        # =============================================================
        # 1.3 - CRÉATION ET REMPLISSAGE COUCHE PRINCIPALE
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.3 - Création et remplissage de la couche principale")
        print(f"{'='*70}")
        
        # Préparation des features
        features_main = []
        count_with_coords = 0
        count_without_coords = 0
        
        for obs in self.observations:
            feature = QgsFeature(fields_main)
            
            # Extraction des coordonnées
            geojson = obs.get("geojson", {})
            coords = geojson.get("coordinates", [None, None]) if geojson else [None, None]
            longitude = coords[0]
            latitude = coords[1]
            
            # Création de la géométrie si coordonnées disponibles
            if longitude is not None and latitude is not None:
                point = QgsPointXY(float(longitude), float(latitude))
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                count_with_coords += 1
            else:
                # Observation sans coordonnées → géométrie nulle
                count_without_coords += 1
            
            # Remplissage des attributs
            for field_name in self.selected_fields:
                field_idx = fields_main.indexOf(field_name)
                if field_idx == -1:
                    continue
                
                # Extraction de la valeur selon le champ
                value = None
                
                if field_name == "inat_id":
                    value = str(obs.get("id")) if obs.get("id") else None
                elif field_name == "date_obs":
                    # Conversion en QDate pour champ Date
                    date_str = obs.get("observed_on")
                    if date_str:
                        try:
                            # Format "YYYY-MM-DD"
                            parts = date_str.split("-")
                            if len(parts) == 3:
                                value = QDate(int(parts[0]), int(parts[1]), int(parts[2]))
                            else:
                                value = None
                        except:
                            value = None
                    else:
                        value = None
                elif field_name == "scientific_name":
                    value = (obs.get("taxon") or {}).get("name")
                elif field_name == "vernacular_name_FR":
                    value = (obs.get("taxon") or {}).get("preferred_common_name")
                elif field_name == "latitude":
                    # Champ Double - valeur numérique directe
                    value = latitude if latitude is not None else None
                elif field_name == "longitude":
                    # Champ Double - valeur numérique directe
                    value = longitude if longitude is not None else None
                elif field_name == "place_guess":
                    value = obs.get("place_guess")
                elif field_name == "taxon_id":
                    tid = (obs.get("taxon") or {}).get("id")
                    value = str(tid) if tid else None
                elif field_name == "taxon_rank":
                    value = (obs.get("taxon") or {}).get("rank")
                elif field_name == "url_obs":
                    value = obs.get("uri")
                elif field_name == "url_taxon":
                    tid = (obs.get("taxon") or {}).get("id")
                    value = f"https://www.inaturalist.org/taxa/{tid}" if tid else None
                elif field_name == "observateur_id":
                    uid = (obs.get("user") or {}).get("id")
                    value = str(uid) if uid else None
                elif field_name == "observateur_name":
                    value = (obs.get("user") or {}).get("login")
                elif field_name == "quality_grade":
                    value = obs.get("quality_grade")
                elif field_name == "precision":
                    # Champ Integer - conversion en entier
                    prec = obs.get("positional_accuracy")
                    if prec is not None:
                        try:
                            value = int(float(prec))  # Conversion via float au cas où
                        except:
                            value = None
                    else:
                        value = None
                elif field_name == "nbr_photos":
                    # Champ Integer - valeur entière directe
                    value = int(obs.get("_nbr_photos", 0))
                
                feature.setAttribute(field_idx, value)
            
            features_main.append(feature)
        
        print(f"✅ Features préparées :")
        print(f"   - {count_with_coords} avec coordonnées")
        print(f"   - {count_without_coords} sans coordonnées")
        print(f"   - Total : {len(features_main)} features")
        
        # Création d'une couche mémoire temporaire pour l'écriture
        print(f"\n📝 Écriture de la couche principale dans le GPKG...")
        
        temp_layer_main = QgsVectorLayer("Point?crs=EPSG:4326", "temp", "memory")
        temp_provider_main = temp_layer_main.dataProvider()
        temp_provider_main.addAttributes(list(fields_main))
        temp_layer_main.updateFields()
        temp_provider_main.addFeatures(features_main)
        temp_layer_main.updateExtents()
        
        # Sauvegarde dans le GPKG
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "GPKG"
        save_options.layerName = self.nom_couche_principale
        save_options.fileEncoding = "UTF-8"
        
        error = QgsVectorFileWriter.writeAsVectorFormatV2(
            temp_layer_main,
            self.gpkg_path,
            QgsCoordinateTransformContext(),
            save_options
        )
        
        if error[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"Phase 1.3 - Erreur écriture couche principale: {error}")
        
        print(f"✅ Couche principale écrite dans le GPKG")
        
        # =============================================================
        # 1.4 - CRÉATION ET REMPLISSAGE TABLE PHOTOS
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.4 - Création et remplissage de la table photos")
        print(f"{'='*70}")
        
        # Préparation des features
        features_photos = []
        
        for photo in self.photos:
            feature = QgsFeature(fields_photos)
            feature.setAttribute("inat_id", str(photo.get("inat_id")))
            feature.setAttribute("photo_rank", photo.get("photo_rank"))
            feature.setAttribute("photo_label", photo.get("photo_label"))
            feature.setAttribute("identifier", photo.get("identifier"))
            features_photos.append(feature)
        
        print(f"✅ Features photos préparées : {len(features_photos)} photos")
        
        # Création d'une couche mémoire temporaire pour l'écriture
        print(f"\n📝 Écriture de la table photos dans le GPKG...")
        
        temp_layer_photos = QgsVectorLayer("None", "temp_photos", "memory")
        temp_provider_photos = temp_layer_photos.dataProvider()
        temp_provider_photos.addAttributes(list(fields_photos))
        temp_layer_photos.updateFields()
        temp_provider_photos.addFeatures(features_photos)
        
        # Sauvegarde dans le GPKG
        save_options_photos = QgsVectorFileWriter.SaveVectorOptions()
        save_options_photos.driverName = "GPKG"
        save_options_photos.layerName = self.nom_couche_photos
        save_options_photos.fileEncoding = "UTF-8"
        save_options_photos.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        
        error_photos = QgsVectorFileWriter.writeAsVectorFormatV2(
            temp_layer_photos,
            self.gpkg_path,
            QgsCoordinateTransformContext(),
            save_options_photos
        )
        
        if error_photos[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"Phase 1.4 - Erreur écriture table photos: {error_photos}")
        
        print(f"✅ Table photos écrite dans le GPKG")
        
        # =============================================================
        # 1.5 - CHARGEMENT DES COUCHES DEPUIS LE GPKG
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.5 - Chargement des couches depuis le GPKG")
        print(f"{'='*70}")
        
        # Chargement couche principale
        uri_main = f"{self.gpkg_path}|layername={self.nom_couche_principale}"
        self.layer_main = QgsVectorLayer(uri_main, self.nom_couche_principale, "ogr")
        
        if not self.layer_main.isValid():
            raise RuntimeError("Phase 1.5 - Couche principale invalide après chargement")
        
        print(f"✅ Couche principale chargée : {self.layer_main.featureCount()} features")
        
        # Chargement table photos
        uri_photos = f"{self.gpkg_path}|layername={self.nom_couche_photos}"
        self.layer_photos = QgsVectorLayer(uri_photos, self.nom_couche_photos, "ogr")
        
        if not self.layer_photos.isValid():
            raise RuntimeError("Phase 1.5 - Table photos invalide après chargement")
        
        print(f"✅ Table photos chargée : {self.layer_photos.featureCount()} features")
        
        # =============================================================
        # 1.6 - AJOUT AU PROJET QGIS
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"1.6 - Ajout au projet QGIS")
        print(f"{'='*70}")
        
        # Ajout des couches au projet (pas encore dans le LayerTree)
        project.addMapLayer(self.layer_main, False)
        project.addMapLayer(self.layer_photos, False)
        
        # Insertion dans le LayerTree
        root = project.layerTreeRoot()
        
        # Recherche de la position du cercle
        cercle_index = None
        for i, layer in enumerate(root.layerOrder()):
            if layer.name() == self.nom_couche_cercle:
                cercle_index = i
                break
        
        # Insertion AU-DESSUS du cercle (ou au début si cercle introuvable)
        if cercle_index is not None:
            # IMPORTANT : cercle_index (sans +1) = AVANT le cercle = AU-DESSUS
            root.insertLayer(cercle_index, self.layer_photos)
            root.insertLayer(cercle_index, self.layer_main)
            print(f"✅ Couches insérées AU-DESSUS de '{self.nom_couche_cercle}'")
        else:
            root.insertLayer(0, self.layer_photos)
            root.insertLayer(0, self.layer_main)
            print(f"⚠️  Cercle non trouvé, couches insérées en haut")
        
        # =============================================================
        # 1.7 - PHASE 1 TERMINÉE
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"✅ PHASE 1 TERMINÉE AVEC SUCCÈS")
        print(f"{'='*70}")
        print(f"GPKG créé          : {self.gpkg_path}")
        print(f"Couche principale  : {self.layer_main.featureCount()} features")
        print(f"Table photos       : {self.layer_photos.featureCount()} features")
        print(f"\n⚠️  ÉTAT ACTUEL :")
        print(f"   ✅ Données sauvegardées dans le GPKG")
        print(f"   ✅ Couches visibles dans QGIS")
        print(f"   ❌ Aucune relation établie (Phase 3)")
        print(f"   ❌ Aucune stylisation appliquée (Phase 3)")
        print(f"{'='*70}\n")
        
        # =============================================================
        # SÉCURISATION DE L'ÉTAT QGIS (solution Perplexity)
        # =============================================================
        # Forcer QGIS dans un état stable pour éviter les crashs au clic
        # sur la table photos sur certaines configurations.
        #
        # Stratégie : S'assurer que QGIS est dans un état sûr à la fin
        # du script, avec un outil sûr actif et la couche principale
        # sélectionnée (pas la table photos).
        
        print(f"🔒 Sécurisation de l'état QGIS...")
        
        canvas = self.iface.mapCanvas()
        
        # 1. Forcer l'outil Pan (sûr pour toutes les couches)
        self.iface.actionPan().trigger()
        
        # 2. Activer la couche PRINCIPALE (qui a des géométries)
        self.iface.setActiveLayer(self.layer_main)
        
        # 3. Refresh forcé du canvas
        canvas.refresh()
        
        print(f"✅ État sécurisé : outil Pan + couche principale active")
        print(f"{'='*70}\n")
        # =============================================================
        
        # Message à l'utilisateur
        # Message de développement - Désactivé en production
        # QMessageBox.information(
        #     self.iface.mainWindow(),
        #     "iNaturalist Import - Phase 1 Complete",
        #     f"✅ Phase 1: Layers created successfully!\n\n"
        #     f"GPKG file: {os.path.basename(self.gpkg_path)}\n"
        #     f"Main layer: {self.layer_main.featureCount()} observations\n"
        #     f"Photos table: {self.layer_photos.featureCount()} photos\n\n"
        #     f"✅ Data saved in GeoPackage format.\n"
        #     f"⚠️  No relation or styling applied yet.\n\n"
        #     f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        #     f"✅ Phase 1 : Couches créées avec succès !\n\n"
        #     f"Fichier GPKG : {os.path.basename(self.gpkg_path)}\n"
        #     f"Couche principale : {self.layer_main.featureCount()} observations\n"
        #     f"Table photos : {self.layer_photos.featureCount()} photos\n\n"
        #     f"✅ Données sauvegardées au format GeoPackage.\n"
        #     f"⚠️  Aucune relation ni stylisation appliquée pour l'instant."
        # )
        
        # =================================================================
        # PHASE 3.1 : Relation + Formulaire table Photos
        # =================================================================
        self._run_phase_3_1()
    
    # =================================================================
    # PHASE 3.1 : RELATION + FORMULAIRE TABLE PHOTOS
    # =================================================================
    
    def _run_phase_3_1(self):
        """
        PHASE 3.1 - Création de la relation 1-N et configuration du formulaire
        de la table photos
        
        - Création de la relation "Photos iNaturalist"
        - Configuration des widgets de formulaire (Hidden, RelationReference, ExternalResource)
        - Configuration du layout (generatedlayout)
        """
        from qgis.core import (
            QgsRelation, QgsEditorWidgetSetup, QgsEditFormConfig
        )
        
        project = QgsProject.instance()
        
        print(f"\n{'='*70}")
        print(f"PHASE 3.1 - Relation + Formulaire table Photos")
        print(f"{'='*70}")
        
        # =============================================================
        # 3.1.1 - CRÉATION DE LA RELATION 1-N
        # =============================================================
        
        print(f"\n3.1.1 - Création de la relation 1-N")
        
        # Créer la relation
        relation = QgsRelation()
        relation.setId("rel_inat_photos")
        relation.setName("Photos iNaturalist")
        relation.setReferencedLayer(self.layer_main.id())      # Couche parent (observations)
        relation.setReferencingLayer(self.layer_photos.id())   # Couche enfant (photos)
        relation.addFieldPair("inat_id", "inat_id")            # Clé étrangère
        
        # Vérifier la validité
        if not relation.isValid():
            print(f"⚠️  Relation invalide - vérifier les champs 'inat_id'")
        else:
            # Ajouter au gestionnaire de relations
            project.relationManager().addRelation(relation)
            print(f"✅ Relation 'Photos iNaturalist' créée")
            print(f"   Parent : {self.layer_main.name()} (observations)")
            print(f"   Enfant : {self.layer_photos.name()} (photos)")
            print(f"   Clé : inat_id → inat_id")
        
        # =============================================================
        # 3.1.2 - CONFIGURATION DES WIDGETS - Table Photos
        # =============================================================
        
        print(f"\n3.1.2 - Configuration des widgets de formulaire")
        
        # Widget Hidden pour fid (si existe)
        if "fid" in [f.name() for f in self.layer_photos.fields()]:
            idx = self.layer_photos.fields().indexOf("fid")
            setup = QgsEditorWidgetSetup('Hidden', {})
            self.layer_photos.setEditorWidgetSetup(idx, setup)
            print(f"✅ fid → Hidden")
        
        # Widget Hidden pour photo_rank
        idx = self.layer_photos.fields().indexOf("photo_rank")
        setup = QgsEditorWidgetSetup('Hidden', {})
        self.layer_photos.setEditorWidgetSetup(idx, setup)
        print(f"✅ photo_rank → Hidden")
        
        # Widget RelationReference pour inat_id
        idx = self.layer_photos.fields().indexOf("inat_id")
        setup = QgsEditorWidgetSetup('RelationReference', {})
        self.layer_photos.setEditorWidgetSetup(idx, setup)
        print(f"✅ inat_id → RelationReference")
        
        # Widget TextEdit pour photo_label (par défaut, mais on le configure explicitement)
        idx = self.layer_photos.fields().indexOf("photo_label")
        setup = QgsEditorWidgetSetup('TextEdit', {})
        self.layer_photos.setEditorWidgetSetup(idx, setup)
        print(f"✅ photo_label → TextEdit")
        
        # Widget ExternalResource pour identifier (avec image viewer)
        idx = self.layer_photos.fields().indexOf("identifier")
        config = {
            'DefaultRoot': '',
            'DocumentViewer': 2,           # Image viewer
            'DocumentViewerHeight': 1,
            'FullUrl': True,
            'RelativeStorage': 0,
            'StorageMode': 0,
            'UseLink': True
        }
        setup = QgsEditorWidgetSetup('ExternalResource', config)
        self.layer_photos.setEditorWidgetSetup(idx, setup)
        print(f"✅ identifier → ExternalResource (avec image viewer)")
        
        # =============================================================
        # 3.1.3 - CONFIGURATION DU LAYOUT DE FORMULAIRE
        # =============================================================
        
        print(f"\n3.1.3 - Configuration du layout de formulaire")
        
        # Table photos : formulaire généré automatiquement
        form_config_photos = self.layer_photos.editFormConfig()
        form_config_photos.setLayout(QgsEditFormConfig.GeneratedLayout)
        self.layer_photos.setEditFormConfig(form_config_photos)
        print(f"✅ Table photos : formulaire généré automatiquement")
        
        # =============================================================
        # 3.1.4 - PHASE 3.1 TERMINÉE
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"✅ PHASE 3.1 TERMINÉE AVEC SUCCÈS")
        print(f"{'='*70}")
        print(f"✅ Relation créée : Photos iNaturalist (1-N)")
        print(f"✅ Widgets configurés :")
        print(f"   - fid : Hidden")
        print(f"   - inat_id : RelationReference")
        print(f"   - photo_rank : Hidden")
        print(f"   - photo_label : TextEdit")
        print(f"   - identifier : ExternalResource (image viewer)")
        print(f"✅ Layout configuré : generatedlayout")
        print(f"{'='*70}\n")
        
        # Message de développement - Désactivé en production
        # QMessageBox.information(
        #     self.iface.mainWindow(),
        #     "iNaturalist Import - Phase 3.1 Complete",
        #     f"✅ Phase 3.1: Relation and Photos form configured!\n\n"
        #     f"Relation: Photos iNaturalist (1-N)\n"
        #     f"Form: Photo viewer enabled\n\n"
        #     f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        #     f"✅ Phase 3.1 : Relation et formulaire Photos configurés !\n\n"
        #     f"Relation : Photos iNaturalist (1-N)\n"
        #     f"Formulaire : Visualiseur de photos activé"
        # )
        
        # =================================================================
        # PHASE 3.2 : Formulaire couche principale
        # =================================================================
        self._run_phase_3_2()
    
    # =================================================================
    # PHASE 3.2 : FORMULAIRE COUCHE PRINCIPALE
    # =================================================================
    
    def _run_phase_3_2(self):
        """
        PHASE 3.2 - Configuration du formulaire de la couche principale
        
        - Configuration des widgets (TextEdit, ExternalResource)
        - Configuration du layout à cadres de groupes
        - Ajout du widget de relation pour afficher les photos
        """
        from qgis.core import (
            QgsEditorWidgetSetup, QgsEditFormConfig, QgsAttributeEditorContainer,
            QgsAttributeEditorField, QgsAttributeEditorRelation
        )
        
        project = QgsProject.instance()
        
        print(f"\n{'='*70}")
        print(f"PHASE 3.2 - Formulaire couche principale")
        print(f"{'='*70}")
        
        # =============================================================
        # 3.2.1 - CONFIGURATION DES WIDGETS - Couche principale
        # =============================================================
        
        print(f"\n3.2.1 - Configuration des widgets de formulaire")
        
        # Liste des champs standards (TextEdit)
        text_edit_fields = [
            "fid", "inat_id", "date_obs", "scientific_name", "vernacular_name_FR",
            "latitude", "longitude", "place_guess", "taxon_id", "taxon_rank",
            "observateur_id", "observateur_name", "quality_grade", "precision", "nbr_photos"
        ]
        
        for field_name in text_edit_fields:
            if field_name in [f.name() for f in self.layer_main.fields()]:
                idx = self.layer_main.fields().indexOf(field_name)
                setup = QgsEditorWidgetSetup('TextEdit', {})
                self.layer_main.setEditorWidgetSetup(idx, setup)
        
        print(f"✅ {len(text_edit_fields)} champs → TextEdit")
        
        # Widget ExternalResource pour url_obs
        if "url_obs" in [f.name() for f in self.layer_main.fields()]:
            idx = self.layer_main.fields().indexOf("url_obs")
            config = {
                'DefaultRoot': '',
                'FullUrl': True,
                'RelativeStorage': 0,
                'StorageMode': 0,
                'UseLink': True
            }
            setup = QgsEditorWidgetSetup('ExternalResource', config)
            self.layer_main.setEditorWidgetSetup(idx, setup)
            print(f"✅ url_obs → ExternalResource (lien cliquable)")
        
        # Widget ExternalResource pour url_taxon
        if "url_taxon" in [f.name() for f in self.layer_main.fields()]:
            idx = self.layer_main.fields().indexOf("url_taxon")
            config = {
                'DefaultRoot': '',
                'FullUrl': True,
                'RelativeStorage': 0,
                'StorageMode': 0,
                'UseLink': True
            }
            setup = QgsEditorWidgetSetup('ExternalResource', config)
            self.layer_main.setEditorWidgetSetup(idx, setup)
            print(f"✅ url_taxon → ExternalResource (lien cliquable)")
        
        # =============================================================
        # 3.2.2 - CONFIGURATION DU LAYOUT À CADRES DE GROUPES
        # =============================================================
        
        print(f"\n3.2.2 - Configuration du layout à cadres de groupes")
        
        # Créer la configuration du formulaire
        form_config = self.layer_main.editFormConfig()
        form_config.setLayout(QgsEditFormConfig.TabLayout)  # Cadres de groupes
        
        # Conteneur racine (2 colonnes)
        root_container = QgsAttributeEditorContainer("", None)
        root_container.setIsGroupBox(True)
        root_container.setColumnCount(2)
        
        # === GROUPE 1 : "Observations" (colonne gauche) ===
        group1 = QgsAttributeEditorContainer("Observations", root_container)
        group1.setIsGroupBox(True)
        group1.setColumnCount(1)
        group1.setHorizontalStretch(3)  # Largeur colonne
        
        # Champs du groupe 1
        group1_fields = [
            "inat_id", "date_obs", "scientific_name", "vernacular_name_FR",
            "latitude", "longitude", "place_guess", "precision"
        ]
        
        for field_name in group1_fields:
            if field_name in [f.name() for f in self.layer_main.fields()]:
                idx = self.layer_main.fields().indexOf(field_name)
                field_widget = QgsAttributeEditorField(field_name, idx, group1)
                group1.addChildElement(field_widget)
        
        root_container.addChildElement(group1)
        
        # === GROUPE 2 : "   " (colonne droite, titre vide) ===
        group2 = QgsAttributeEditorContainer("   ", root_container)
        group2.setIsGroupBox(True)
        group2.setColumnCount(1)
        group2.setHorizontalStretch(3)  # Largeur colonne
        
        # Champs du groupe 2
        group2_fields = [
            "taxon_id", "taxon_rank", "url_obs", "url_taxon",
            "observateur_id", "observateur_name", "quality_grade"
        ]
        
        for field_name in group2_fields:
            if field_name in [f.name() for f in self.layer_main.fields()]:
                idx = self.layer_main.fields().indexOf(field_name)
                field_widget = QgsAttributeEditorField(field_name, idx, group2)
                group2.addChildElement(field_widget)
        
        root_container.addChildElement(group2)
        
        # Appliquer le conteneur 2 colonnes AVANT d'ajouter la relation
        form_config.clearTabs()
        form_config.addTab(root_container)
        
        # === WIDGET RELATION : Photos iNaturalist (HORS colonnes) ===
        # Récupérer la relation créée en Phase 3.1
        relation = project.relationManager().relation("rel_inat_photos")
        
        if relation.isValid():
            # Créer un nouveau conteneur racine pour la relation
            # (qui sera au même niveau que root_container, donc HORS colonnes)
            relation_widget = QgsAttributeEditorRelation(
                relation.name(),
                relation,
                None  # Pas de parent = au niveau racine
            )
            # Configuration du widget relation (éditeur de relation)
            relation_widget.setRelationWidgetTypeId("relation_editor")
            
            # Ajouter directement au formulaire (pas dans root_container)
            form_config.addTab(relation_widget)
            print(f"✅ Widget relation 'Photos iNaturalist' ajouté HORS colonnes")
        else:
            print(f"⚠️  Relation 'rel_inat_photos' non trouvée")
        
        self.layer_main.setEditFormConfig(form_config)
        
        print(f"✅ Layout configuré : 2 groupes + widget relation")
        
        # =============================================================
        # 3.2.3 - PHASE 3.2 TERMINÉE
        # =============================================================
        
        print(f"\n{'='*70}")
        print(f"✅ PHASE 3.2 TERMINÉE AVEC SUCCÈS")
        print(f"{'='*70}")
        print(f"✅ Widgets configurés :")
        print(f"   - 15 champs : TextEdit")
        print(f"   - url_obs : ExternalResource")
        print(f"   - url_taxon : ExternalResource")
        print(f"✅ Layout configuré :")
        print(f"   - Groupe 1 'Observations' (8 champs)")
        print(f"   - Groupe 2 '   ' (7 champs)")
        print(f"   - Widget relation 'Photos iNaturalist'")
        print(f"{'='*70}\n")
        
        # Message de développement - Désactivé en production
        # QMessageBox.information(
        #     self.iface.mainWindow(),
        #     "iNaturalist Import - Phase 3.2 Complete",
        #     f"✅ Phase 3.2: Main layer form configured!\n\n"
        #     f"Form layout: 2 groups + photo viewer\n"
        #     f"Widgets: URLs clickable\n\n"
        #     f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        #     f"✅ Phase 3.2 : Formulaire couche principale configuré !\n\n"
        #     f"Layout : 2 groupes + visualiseur de photos\n"
        #     f"Widgets : URLs cliquables"
        # )
        
        # =================================================================
        # PHASE 3.3 : Symbologie couche principale
        # =================================================================
        # PHASE 3.3 : Symbologie - SUPPRIMÉE (sera faite par Script 2)
        
        # =================================================================
        # PHASE 4 : Finalisation
        # =================================================================
        self._run_phase_4()
    # =================================================================
    # PHASE 4 : FINALISATION
    # =================================================================
    
    def _run_phase_4(self):
        """
        PHASE 4 - Finalisation et message récapitulatif
        
        - Retour au SCU d'origine
        - Calcul des statistiques
        - Affichage du message final bilingue avec instructions
        """
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QTextBrowser
        from qgis.PyQt.QtGui import QPixmap
        
        project = QgsProject.instance()
        
        print(f"\n{'='*70}")
        print(f"PHASE 4 - Finalisation")
        print(f"{'='*70}")
        
        # =============================================================
        # 4.1 - RETOUR AU SCU D'ORIGINE
        # =============================================================
        
        print(f"\n4.1 - Retour au SCU d'origine")
        
        if hasattr(self, 'scu_origine') and self.scu_origine:
            project.setCrs(self.scu_origine)
            self.iface.mapCanvas().setDestinationCrs(self.scu_origine)
            self.iface.mapCanvas().refresh()
            print(f"✅ SCU restauré : {self.scu_origine.authid()}")
        else:
            print(f"⚠️  SCU d'origine non trouvé, conservation du SCU actuel")
        
        # =============================================================
        # 4.2 - CALCUL DES STATISTIQUES
        # =============================================================
        
        print(f"\n4.2 - Calcul des statistiques")
        
        # Nombre d'observations
        nb_observations = self.layer_main.featureCount()
        
        # Nombre de taxons distincts
        idx_scientific_name = self.layer_main.fields().indexOf("scientific_name")
        unique_taxa = self.layer_main.uniqueValues(idx_scientific_name)
        nb_taxons = len(unique_taxa)
        
        # Nombre de photos
        nb_photos = self.layer_photos.featureCount()
        
        print(f"📊 Statistiques :")
        print(f"   - Observations : {nb_observations}")
        print(f"   - Taxons distincts : {nb_taxons}")
        print(f"   - Photos : {nb_photos}")
        
        # =============================================================
        # 4.3 - MESSAGE FINAL BILINGUE
        # =============================================================
        
        print(f"\n4.3 - Affichage du message final")
        
        # Chemin vers l'icône du plugin
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, "icons", "mActionIdentify.png")
        
        print(f"\n{'='*70}")
        print(f"✅ PHASE 4 TERMINÉE - IMPORT COMPLET")
        print(f"{'='*70}\n")
        
        # =========================================================
        # POINT FINAL : Enchainement automatique avec Script 2
        # =========================================================
        print(f"\n{'='*70}")
        print(f"🔄 LANCEMENT AUTOMATIQUE DU SCRIPT 2 - ENRICHISSEMENT TAXONOMIQUE")
        print(f"{'='*70}\n")
        
        from .yd_Script_2 import yd_run as yd_run_script_2
        
        # Créer un contexte avec les infos du Script 1
        context = {
            'latitude_centre': self.latitude_centre,
            'longitude_centre': self.longitude_centre,
            'rayon_metres': self.rayon_metres,
            'dossier_projet': self.dossier_projet,
            'nb_observations': nb_observations,
            'nb_taxons': nb_taxons,
            'nb_photos': nb_photos
        }
        
        script_2 = yd_run_script_2(self.iface)
        script_2.run(context)  # Passer le contexte
        
        print(f"\n{'='*70}")
        print(f"✅ SCRIPT COMPLET TERMINÉ AVEC SUCCÈS (Script 1 + Script 2)")
        print(f"{'='*70}\n")
    

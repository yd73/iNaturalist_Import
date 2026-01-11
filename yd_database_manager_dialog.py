"""
Interface de gestion de la base de données taxonomique mondiale.

Dialog PyQt5 pour :
- Visualiser le statut de la BDD
- Télécharger/Mettre à jour la BDD
- Voir les changements entre versions
- Gérer les paramètres
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

try:
    from qgis.PyQt.QtCore import Qt, QTimer
    from qgis.PyQt.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QTextEdit, QGroupBox, QMessageBox, QTabWidget,
        QWidget, QTableWidget, QTableWidgetItem, QHeaderView
    )
    from qgis.PyQt.QtGui import QFont
except ImportError:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QTextEdit, QGroupBox, QMessageBox, QTabWidget,
        QWidget, QTableWidget, QTableWidgetItem, QHeaderView
    )
    from PyQt5.QtGui import QFont

from .yd_taxonomy_database import TaxonomyDatabase
from .yd_database_downloader import DatabaseDownloader


class DatabaseManagerDialog(QDialog):
    """
    Dialog de gestion de la base de données taxonomique.
    """
    
    def __init__(self, plugin_dir: str, parent=None):
        """
        Initialise le dialog.
        
        Args:
            plugin_dir: Répertoire du plugin
            parent: Widget parent
        """
        super().__init__(parent)
        self.plugin_dir = Path(plugin_dir)
        self.db = TaxonomyDatabase(str(plugin_dir))
        self.downloader = None
        self.changes_report = None
        
        self.setWindowTitle("iNaturalist Taxonomy Database Manager / Gestionnaire de Base Taxonomique")
        self.setMinimumSize(700, 500)
        
        self._setup_ui()
        self._load_status()
    
    # ==========================================================================
    # INTERFACE UTILISATEUR
    # ==========================================================================
    
    def _setup_ui(self):
        """Configure l'interface utilisateur."""
        layout = QVBoxLayout()
        
        # Onglets (seulement 2 maintenant)
        tabs = QTabWidget()
        tabs.addTab(self._create_status_tab(), "📊 Status / Statut")
        tabs.addTab(self._create_changes_tab(), "📋 Changes / Changements")
        
        layout.addWidget(tabs)
        
        # Boutons du bas
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close / Fermer")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _create_status_tab(self) -> QWidget:
        """
        Crée l'onglet de statut.
        
        Returns:
            QWidget: Widget de l'onglet
        """
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Groupe d'information
        info_group = QGroupBox("Database Information")
        info_layout = QVBoxLayout()
        
        # Labels de statut
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(10)
        self.status_label.setFont(font)
        
        info_layout.addWidget(self.status_label)
        info_group.setLayout(info_layout)
        
        layout.addWidget(info_group)
        
        # Barre de progression (cachée par défaut)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Label de statut de téléchargement (caché par défaut)
        self.download_status_label = QLabel()
        self.download_status_label.setWordWrap(True)
        self.download_status_label.setVisible(False)
        layout.addWidget(self.download_status_label)
        
        # Boutons d'action
        action_layout = QHBoxLayout()
        
        self.download_button = QPushButton("⬇️ Download/Update Database / Télécharger/Mettre à jour la base")
        self.download_button.clicked.connect(self._start_download)
        action_layout.addWidget(self.download_button)
        
        self.cancel_button = QPushButton("❌ Cancel / Annuler")
        self.cancel_button.clicked.connect(self._cancel_download)
        self.cancel_button.setVisible(False)
        action_layout.addWidget(self.cancel_button)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        layout.addStretch()
        widget.setLayout(layout)
        
        return widget
    
    def _create_changes_tab(self) -> QWidget:
        """
        Crée l'onglet de rapport de changements.
        
        Returns:
            QWidget: Widget de l'onglet
        """
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Label d'information
        self.changes_info_label = QLabel(
            "Changes between old and new database versions will appear here\n"
            "after downloading a new version.\n\n"
            "Les changements entre les anciennes et nouvelles versions de la base\n"
            "apparaîtront ici après le téléchargement d'une nouvelle version."
        )
        self.changes_info_label.setWordWrap(True)
        layout.addWidget(self.changes_info_label)
        
        # Texte de changements
        self.changes_text = QTextEdit()
        self.changes_text.setReadOnly(True)
        self.changes_text.setVisible(False)
        layout.addWidget(self.changes_text)
        
        widget.setLayout(layout)
        
        return widget
    
    # ==========================================================================
    # CHARGEMENT DU STATUT
    # ==========================================================================
    
    def _load_status(self):
        """Charge et affiche le statut de la BDD."""
        stats = self.db.get_statistics()
        emoji, status_label = self.db.get_status_emoji()
        
        if stats['status'] == 'not_installed':
            status_html = f"""
            <h3>{emoji} Database Status / Statut: {status_label}</h3>
            <p><b>The taxonomy database is not installed.</b></p>
            <p><b>La base de données taxonomique n'est pas installée.</b></p>
            <p>Download it from the "Download/Update" tab to enable fast local lookups.</p>
            <p>Téléchargez-la depuis l'onglet "Download/Update" pour activer les recherches locales rapides.</p>
            """
        else:
            age_text = f"{stats['age_days']} days old / jours" if stats['age_days'] is not None else "Unknown age / Âge inconnu"
            
            status_html = f"""
            <h3>{emoji} Database Status / Statut: {status_label}</h3>
            <table style='width: 100%;'>
                <tr>
                    <td><b>Version:</b></td>
                    <td>{stats['version'] or 'Unknown / Inconnue'}</td>
                </tr>
                <tr>
                    <td><b>Installed / Installée:</b></td>
                    <td>{stats['install_date'] or 'Unknown / Inconnue'}</td>
                </tr>
                <tr>
                    <td><b>Age / Âge:</b></td>
                    <td>{age_text}</td>
                </tr>
                <tr>
                    <td><b>Total Taxa / Taxons:</b></td>
                    <td>{stats['total_taxa']:,}</td>
                </tr>
                <tr>
                    <td><b>Database Size / Taille:</b></td>
                    <td>{stats['size_mb']} MB</td>
                </tr>
            </table>
            """
            
            # Recommandation de mise à jour
            if stats['status'] in ['old', 'very_old']:
                status_html += "<p><b>⚠️ Update recommended! / Mise à jour recommandée !</b> The database is getting old. / La base vieillit.</p>"
            elif stats['status'] == 'aging':
                status_html += "<p><b>💡 Tip / Conseil:</b> Consider updating in the next few weeks. / Envisagez une mise à jour dans les prochaines semaines.</p>"
        
        self.status_label.setText(status_html)
    
    # ==========================================================================
    # TÉLÉCHARGEMENT
    # ==========================================================================
    
    def _start_download(self):
        """Démarre le téléchargement de la BDD."""
        # Demander confirmation
        reply = QMessageBox.question(
            self,
            "Download Database / Télécharger la base",
            "This will download ~80 MB of data and create the taxonomy database.\n"
            "The process takes about 5 seconds.\n\n"
            "Cela téléchargera ~80 Mo de données et créera la base taxonomique.\n"
            "Le processus prend environ 5 secondes.\n\n"
            "Continue / Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Préparer l'interface
        self.download_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.download_status_label.setVisible(True)
        self.download_status_label.setText("Starting download...")
        
        # Créer le downloader (nouveau : juste plugin_dir)
        self.downloader = DatabaseDownloader(str(self.plugin_dir), self)
        
        # Connecter les signaux (adaptés au nouveau downloader)
        self.downloader.progress_updated.connect(self._on_progress_updated)
        self.downloader.download_finished.connect(self._on_download_finished_new)
        
        # Démarrer
        self.downloader.start()
    
    def _cancel_download(self):
        """Annule le téléchargement."""
        if self.downloader:
            self.downloader.stop()
            self.download_status_label.setText("Cancelling...")
    
    def _on_progress_updated(self, percent: int, message: str):
        """
        Handler pour le signal progress_updated du nouveau downloader.
        
        Args:
            percent: Pourcentage (0-100)
            message: Message de statut
        """
        self.progress_bar.setValue(percent)
        self.download_status_label.setText(message)
    
    def _on_download_finished_new(self, success: bool, message: str):
        """
        Handler pour le signal download_finished du nouveau downloader.
        
        Args:
            success: True si succès
            message: Message final
        """
        # Réinitialiser l'interface
        self.download_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.download_status_label.setVisible(False)
        
        if success:
            # Recharger le statut
            self._load_status()
            
            # Message de succès
            QMessageBox.information(
                self,
                "Download Complete / Téléchargement terminé",
                f"{message}\n\n"
                "The database is now ready to use.\n"
                "Script 2 will use it automatically for ultra-fast taxonomy lookups!\n\n"
                "La base de données est maintenant prête à l'emploi.\n"
                "Le Script 2 l'utilisera automatiquement pour des recherches taxonomiques ultra-rapides !"
            )
        else:
            # Message d'erreur
            QMessageBox.critical(
                self,
                "Download Failed / Échec du téléchargement",
                f"Failed to download database / Échec du téléchargement:\n\n{message}"
            )
    
    def _on_download_progress(self, downloaded: int, total: int, speed_mbps: float, eta_seconds: int):
        """
        Callback de progression du téléchargement.
        
        Args:
            downloaded: Octets téléchargés
            total: Taille totale
            speed_mbps: Vitesse en MB/s
            eta_seconds: Temps restant estimé
        """
        # Pourcentage
        percent = int(downloaded / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        
        # Formatage
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        
        # ETA
        if eta_seconds < 60:
            eta_str = f"{eta_seconds} seconds"
        else:
            eta_min = eta_seconds // 60
            eta_sec = eta_seconds % 60
            eta_str = f"{eta_min}m {eta_sec}s"
        
        # Mise à jour du label
        status_text = (
            f"Downloading: {downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percent}%)\n"
            f"Speed: {speed_mbps:.2f} MB/s  |  Time remaining: ~{eta_str}"
        )
        self.download_status_label.setText(status_text)
    
    def _on_status_update(self, status: str):
        """
        Callback de mise à jour du statut.
        
        Args:
            status: Message de statut
        """
        self.download_status_label.setText(status)
    
    def _on_download_finished(self, success: bool, db_path: str, changes_report: Dict):
        """
        Callback de fin de téléchargement.
        
        Args:
            success: True si succès
            db_path: Chemin de la nouvelle BDD
            changes_report: Rapport de changements
        """
        self.changes_report = changes_report
        
        # Réinitialiser l'interface
        self.download_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        
        if success:
            self.progress_bar.setValue(100)
            self.download_status_label.setText("✅ Download completed successfully!")
            
            # Afficher le rapport de changements
            self._display_changes_report(changes_report)
            
            # Proposer l'activation
            self._propose_activation(db_path, changes_report)
        else:
            self.download_status_label.setText("❌ Download cancelled.")
    
    def _on_download_error(self, error_message: str):
        """
        Callback d'erreur de téléchargement.
        
        Args:
            error_message: Message d'erreur
        """
        self.download_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.progress_bar.setVisible(False)
        
        QMessageBox.critical(
            self,
            "Download Error",
            f"An error occurred during download:\n\n{error_message}"
        )
    
    # ==========================================================================
    # ACTIVATION DE LA NOUVELLE VERSION
    # ==========================================================================
    
    def _propose_activation(self, new_db_path: str, changes_report: Dict):
        """
        Propose d'activer la nouvelle BDD.
        
        Args:
            new_db_path: Chemin de la nouvelle BDD
            changes_report: Rapport de changements
        """
        # Construire le message
        if changes_report.get('has_old_db'):
            message = (
                f"✅ New database downloaded successfully!\n\n"
                f"📊 Changes:\n"
                f"  • +{changes_report.get('total_added', 0):,} new taxa added\n"
                f"  • {changes_report.get('total_updated', 0):,} taxa updated\n"
                f"  • {changes_report.get('total_removed', 0):,} taxa removed\n\n"
                f"Would you like to activate the new database now?"
            )
        else:
            message = (
                f"✅ Database downloaded successfully!\n\n"
                f"📊 Total taxa: {changes_report.get('total_new', 0):,}\n\n"
                f"Would you like to activate the database now?"
            )
        
        reply = QMessageBox.question(
            self,
            "Activate New Database",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self._activate_database(new_db_path)
    
    def _activate_database(self, new_db_path: str):
        """
        Active la nouvelle base de données.
        
        Args:
            new_db_path: Chemin de la nouvelle BDD
        """
        try:
            import shutil
            
            cache_dir = self.plugin_dir / "iNaturalist_Taxonomy_Cache"
            active_path = cache_dir / "inat_taxonomy_active.db"
            backup_path = cache_dir / "inat_taxonomy_backup.db"
            
            # Backup de l'ancienne BDD si elle existe
            if active_path.exists():
                shutil.move(str(active_path), str(backup_path))
            
            # Activation de la nouvelle
            shutil.move(new_db_path, str(active_path))
            
            # Mise à jour des métadonnées
            metadata = self.db.get_metadata()
            metadata['active_database'] = {
                'version': datetime.now().strftime('%Y-%m-%d'),
                'install_date': datetime.now().isoformat(),
                'taxa_count': self.changes_report.get('total_new', 0),
                'size_mb': active_path.stat().st_size / (1024 * 1024)
            }
            self.db.save_metadata(metadata)
            
            # Succès
            QMessageBox.information(
                self,
                "Database Activated",
                "✅ The new database has been activated successfully!\n\n"
                "The plugin will now use this version for all taxonomy lookups."
            )
            
            # Recharger le statut
            self._load_status()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Activation Error",
                f"Failed to activate the new database:\n\n{str(e)}"
            )
    
    # ==========================================================================
    # RAPPORT DE CHANGEMENTS
    # ==========================================================================
    
    def _display_changes_report(self, changes_report: Dict):
        """
        Affiche le rapport de changements.
        
        Args:
            changes_report: Rapport de changements
        """
        if not changes_report.get('has_old_db'):
            self.changes_info_label.setText(
                f"📊 New database installed\n"
                f"Total taxa: {changes_report.get('total_new', 0):,}"
            )
            return
        
        # Construire le texte HTML
        html = "<h3>📋 Database Changes Report</h3>"
        html += f"<p>Old version: {changes_report.get('total_old', 0):,} taxa</p>"
        html += f"<p>New version: {changes_report.get('total_new', 0):,} taxa</p>"
        html += "<hr>"
        
        # Ajoutés
        added = changes_report.get('added', [])
        total_added = changes_report.get('total_added', len(added))
        html += f"<h4>✅ Added Taxa ({total_added:,})</h4>"
        if added:
            html += "<ul>"
            for item in added[:20]:  # Premiers 20
                html += f"<li><b>{item['name']}</b> ({item['rank']}) - ID: {item['taxon_id']}</li>"
            html += "</ul>"
            if total_added > 20:
                html += f"<p><i>... and {total_added - 20:,} more</i></p>"
        
        # Modifiés
        updated = changes_report.get('updated', [])
        total_updated = changes_report.get('total_updated', len(updated))
        html += f"<h4>🔄 Updated Taxa ({total_updated:,})</h4>"
        if updated:
            html += "<ul>"
            for item in updated[:20]:
                html += f"<li><b>{item['old_name']}</b> → <b>{item['new_name']}</b> (ID: {item['taxon_id']})</li>"
            html += "</ul>"
            if total_updated > 20:
                html += f"<p><i>... and {total_updated - 20:,} more</i></p>"
        
        # Supprimés
        removed = changes_report.get('removed', [])
        total_removed = changes_report.get('total_removed', len(removed))
        html += f"<h4>❌ Removed Taxa ({total_removed:,})</h4>"
        if removed:
            html += "<ul>"
            for item in removed[:20]:
                html += f"<li><b>{item['name']}</b> ({item['rank']}) - ID: {item['taxon_id']}</li>"
            html += "</ul>"
            if total_removed > 20:
                html += f"<p><i>... and {total_removed - 20:,} more</i></p>"
        
        self.changes_text.setHtml(html)
        self.changes_text.setVisible(True)
        self.changes_info_label.setVisible(False)
    
    # ==========================================================================
    # VÉRIFICATION DES MISES À JOUR
    # ==========================================================================


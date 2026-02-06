"""
Module de téléchargement et création de la base de données taxonomique iNaturalist.

Ce module gère l'ensemble du processus :
1. Téléchargement depuis iNaturalist.org
2. Extraction du Darwin Core Archive
3. Parsing des données taxonomiques
4. Construction de la hiérarchie
5. Création de la base SQLite
6. Installation et nettoyage

Interface graphique intégrée dans QGIS avec barre de progression.

Compatible avec plugin v2.0.0, 2.1.0 et 2.2.0
"""

import sqlite3
import requests
import zipfile
import csv
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from qgis.PyQt.QtCore import QThread, pyqtSignal


class DatabaseDownloader(QThread):
    """
    Thread pour télécharger et créer la base de données sans bloquer QGIS.
    """
    
    # Signaux pour communiquer avec l'interface
    progress_updated = pyqtSignal(int, str)  # (pourcentage, message)
    download_finished = pyqtSignal(bool, str)  # (succès, message)
    
    # Configuration
    INAT_TAXONOMY_URL = "https://www.inaturalist.org/taxa/inaturalist-taxonomy.dwca.zip"
    
    def __init__(self, plugin_dir: str, parent=None):
        """
        Initialise le downloader.
        
        Args:
            plugin_dir: Répertoire du plugin
            parent: Widget parent Qt
        """
        super().__init__(parent)
        
        self.plugin_dir = Path(plugin_dir)
        self.cache_dir = self.plugin_dir / "iNaturalist_Taxonomy_Cache"
        self.temp_dir = self.plugin_dir / "temp_taxonomy"
        
        self.db_path = self.cache_dir / "inat_taxonomy_active.db"
        self.backup_path = self.cache_dir / "inat_taxonomy_backup.db"
        self.metadata_path = self.cache_dir / "metadata.json"
        
        self._should_stop = False
    
    def stop(self):
        """Demande l'arrêt du téléchargement."""
        self._should_stop = True
    
    def run(self):
        """Exécute le processus complet de téléchargement et création."""
        try:
            # Créer les dossiers nécessaires
            self.cache_dir.mkdir(exist_ok=True)
            self.temp_dir.mkdir(exist_ok=True)
            
            # Étape 1: Backup si nécessaire
            if self.db_path.exists():
                self.progress_updated.emit(0, "💾 Création du backup de l'ancienne BDD...")
                self._backup_existing_database()
            
            # Étape 2: Téléchargement
            self.progress_updated.emit(5, "📥 Téléchargement depuis iNaturalist.org...")
            zip_path = self.temp_dir / "inat_taxonomy.dwca.zip"
            
            if not self._download_file(self.INAT_TAXONOMY_URL, zip_path):
                self.download_finished.emit(False, "Échec du téléchargement")
                return
            
            if self._should_stop:
                self._cleanup()
                self.download_finished.emit(False, "Téléchargement annulé")
                return
            
            # Étape 3: Extraction
            self.progress_updated.emit(15, "📦 Extraction de l'archive...")
            extract_dir = self.temp_dir / "extracted"
            
            if not self._extract_archive(zip_path, extract_dir):
                self._cleanup()
                self.download_finished.emit(False, "Échec de l'extraction")
                return
            
            if self._should_stop:
                self._cleanup()
                self.download_finished.emit(False, "Extraction annulée")
                return
            
            # Étape 4: Parsing
            self.progress_updated.emit(25, "📖 Lecture des données taxonomiques...")
            taxon_file = extract_dir / "taxa.csv"
            
            if not taxon_file.exists():
                self._cleanup()
                self.download_finished.emit(False, f"Fichier taxa.csv non trouvé")
                return
            
            taxa = self._parse_taxon_file(taxon_file)
            
            if self._should_stop:
                self._cleanup()
                self.download_finished.emit(False, "Parsing annulé")
                return
            
            # Étape 5: Construction hiérarchie
            self.progress_updated.emit(50, "🌳 Construction de la hiérarchie taxonomique...")
            enriched_taxa = self._build_taxonomy_hierarchy(taxa)
            
            if self._should_stop:
                self._cleanup()
                self.download_finished.emit(False, "Construction annulée")
                return
            
            # Étape 6: Création BDD
            self.progress_updated.emit(70, "🗄️ Création de la base de données...")
            temp_db_path = self.temp_dir / "inat_taxonomy_world.db"
            
            if not self._create_database(temp_db_path, enriched_taxa):
                self._cleanup()
                self.download_finished.emit(False, "Échec de la création de la BDD")
                return
            
            if self._should_stop:
                self._cleanup()
                self.download_finished.emit(False, "Création BDD annulée")
                return
            
            # Étape 7: Installation
            self.progress_updated.emit(90, "📥 Installation de la base de données...")
            
            if not self._install_database(temp_db_path):
                self._cleanup()
                self.download_finished.emit(False, "Échec de l'installation")
                return
            
            # Étape 8: Métadonnées
            self.progress_updated.emit(95, "📝 Création des métadonnées...")
            self._create_metadata(len(enriched_taxa))
            
            # Étape 9: Nettoyage
            self.progress_updated.emit(98, "🧹 Nettoyage des fichiers temporaires...")
            self._cleanup()
            
            # Succès !
            self.progress_updated.emit(100, "✅ Base de données installée avec succès !")
            self.download_finished.emit(True, f"✅ {len(enriched_taxa):,} taxons installés")
            
        except Exception as e:
            self._cleanup()
            self.download_finished.emit(False, f"Erreur: {str(e)}")
    
    def _download_file(self, url: str, dest: Path) -> bool:
        """Télécharge un fichier avec mise à jour de la progression."""
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._should_stop:
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            pct = 5 + int((downloaded / total_size) * 10)
                            mb_downloaded = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            self.progress_updated.emit(
                                pct,
                                f"📥 Téléchargement... {mb_downloaded:.1f} / {mb_total:.1f} MB"
                            )
            
            return True
            
        except Exception as e:
            print(f"Erreur téléchargement: {e}")
            return False
    
    def _extract_archive(self, zip_path: Path, extract_dir: Path) -> bool:
        """Extrait l'archive ZIP."""
        try:
            extract_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            return True
            
        except Exception as e:
            print(f"Erreur extraction: {e}")
            return False
    
    def _parse_taxon_file(self, taxon_file: Path) -> Dict:
        """Parse le fichier taxa.csv."""
        taxa = {}
        total_lines = sum(1 for _ in open(taxon_file, 'r', encoding='utf-8')) - 1
        
        delimiter = ',' if taxon_file.suffix == '.csv' else '\t'
        
        with open(taxon_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            
            for idx, row in enumerate(reader, 1):
                if self._should_stop:
                    return {}
                
                taxon_id_raw = row.get('id', '')
                if not taxon_id_raw:
                    continue
                
                if 'inaturalist.org/taxa/' in str(taxon_id_raw):
                    taxon_id = int(taxon_id_raw.split('/')[-1])
                else:
                    try:
                        taxon_id = int(taxon_id_raw)
                    except (ValueError, TypeError):
                        continue
                
                if taxon_id == 0:
                    continue
                
                parent_id_raw = row.get('parentNameUsageID', '')
                parent_id = None
                if parent_id_raw:
                    if 'inaturalist.org/taxa/' in str(parent_id_raw):
                        try:
                            parent_id = int(parent_id_raw.split('/')[-1])
                        except (ValueError, IndexError):
                            parent_id = None
                    else:
                        try:
                            parent_id = int(parent_id_raw)
                        except (ValueError, TypeError):
                            parent_id = None
                
                taxa[taxon_id] = {
                    'taxon_id': taxon_id,
                    'name': row.get('scientificName', ''),
                    'rank': row.get('taxonRank', '').lower(),
                    'parent_id': parent_id
                }
                
                if idx % 10000 == 0:
                    pct = 25 + int((idx / total_lines) * 25)
                    self.progress_updated.emit(pct, f"📖 Lecture... {idx:,} / {total_lines:,} taxons")
        
        return taxa
    
    def _build_taxonomy_hierarchy(self, taxa: Dict) -> Dict:
        """Construit la hiérarchie taxonomique complète."""
        def get_ancestors(taxon_id: int, taxa: dict) -> list:
            ancestors = []
            current_id = taxon_id
            seen = set()
            
            while current_id and current_id in taxa:
                if current_id in seen:
                    break
                seen.add(current_id)
                
                ancestors.append(current_id)
                parent_id = taxa[current_id].get('parent_id')
                
                if not parent_id or parent_id == current_id:
                    break
                
                current_id = parent_id
            
            return ancestors
        
        enriched_taxa = {}
        total = len(taxa)
        
        for idx, (taxon_id, taxon_info) in enumerate(taxa.items(), 1):
            if self._should_stop:
                return {}
            
            ancestor_ids = get_ancestors(taxon_id, taxa)
            
            taxonomy = {
                'kingdom': '', 'phylum': '', 'class': '', 'order': '',
                'family': '', 'genus': '', 'species': ''
            }
            
            for ancestor_id in ancestor_ids:
                ancestor = taxa.get(ancestor_id)
                if ancestor:
                    rank = ancestor['rank']
                    name = ancestor['name']
                    
                    if rank in taxonomy:
                        taxonomy[rank] = name
            
            enriched_taxa[taxon_id] = {
                'taxon_id': taxon_id,
                'name': taxon_info['name'],
                'rank': taxon_info['rank'],
                'kingdom': taxonomy['kingdom'],
                'phylum': taxonomy['phylum'],
                'class': taxonomy['class'],
                'order': taxonomy['order'],
                'family': taxonomy['family'],
                'genus': taxonomy['genus'],
                'species': taxonomy['species'],
                'ancestor_ids': ancestor_ids
            }
            
            if idx % 10000 == 0:
                pct = 50 + int((idx / total) * 20)
                self.progress_updated.emit(pct, f"🌳 Construction... {idx:,} / {total:,} taxons")
        
        return enriched_taxa
    
    def _create_database(self, db_path: Path, taxa: Dict) -> bool:
        """Crée la base de données SQLite."""
        try:
            if db_path.exists():
                db_path.unlink()
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE taxonomy (
                    taxon_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    rank TEXT NOT NULL,
                    kingdom TEXT,
                    phylum TEXT,
                    class TEXT,
                    "order" TEXT,
                    family TEXT,
                    genus TEXT,
                    species TEXT,
                    ancestor_ids TEXT
                )
            """)
            
            cursor.execute("CREATE INDEX idx_taxon_id ON taxonomy(taxon_id)")
            cursor.execute("CREATE INDEX idx_rank ON taxonomy(rank)")
            cursor.execute("CREATE INDEX idx_kingdom ON taxonomy(kingdom)")
            
            cursor.execute("""
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            cursor.execute(
                "INSERT INTO metadata (key, value) VALUES ('version', ?)",
                (datetime.now().strftime('%Y-%m-%d'),)
            )
            
            cursor.execute(
                "INSERT INTO metadata (key, value) VALUES ('source', 'iNaturalist Official Export')"
            )
            
            conn.commit()
            
            batch_size = 1000
            batch = []
            total = len(taxa)
            
            for idx, (taxon_id, taxon_info) in enumerate(taxa.items(), 1):
                if self._should_stop:
                    conn.close()
                    return False
                
                batch.append((
                    taxon_info['taxon_id'],
                    taxon_info['name'],
                    taxon_info['rank'],
                    taxon_info['kingdom'],
                    taxon_info['phylum'],
                    taxon_info['class'],
                    taxon_info['order'],
                    taxon_info['family'],
                    taxon_info['genus'],
                    taxon_info['species'],
                    json.dumps(taxon_info['ancestor_ids'])
                ))
                
                if len(batch) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO taxonomy 
                        (taxon_id, name, rank, kingdom, phylum, class, "order", family, genus, species, ancestor_ids)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                    conn.commit()
                    batch = []
                    
                    pct = 70 + int((idx / total) * 20)
                    self.progress_updated.emit(pct, f"💾 Insertion... {idx:,} / {total:,} taxons")
            
            if batch:
                cursor.executemany("""
                    INSERT INTO taxonomy 
                    (taxon_id, name, rank, kingdom, phylum, class, "order", family, genus, species, ancestor_ids)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
            
            cursor.execute("ANALYZE")
            cursor.execute("VACUUM")
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"Erreur création BDD: {e}")
            return False
    
    def _backup_existing_database(self):
        """Crée un backup de la base existante."""
        try:
            if self.db_path.exists():
                shutil.copy2(self.db_path, self.backup_path)
        except Exception as e:
            print(f"Erreur backup: {e}")
    
    def _install_database(self, temp_db_path: Path) -> bool:
        """Installe la base de données dans le dossier final."""
        try:
            shutil.copy2(temp_db_path, self.db_path)
            return True
        except Exception as e:
            print(f"Erreur installation: {e}")
            return False
    
    def _create_metadata(self, taxa_count: int):
        """Crée le fichier metadata.json."""
        try:
            size_mb = self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
            
            metadata = {
                "version": "1.0",
                "active_database": {
                    "filename": "inat_taxonomy_active.db",
                    "install_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "version": "1.0.0",
                    "source": "iNaturalist Official Export",
                    "taxa_count": taxa_count,
                    "size_mb": round(size_mb, 2),
                    "checksum": "auto"
                },
                "update_settings": {
                    "auto_check": True,
                    "check_frequency_days": 30,
                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Erreur création metadata: {e}")
    
    def _cleanup(self):
        """Supprime tous les fichiers temporaires."""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"Erreur nettoyage: {e}")

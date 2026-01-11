"""
Module de gestion de la base de données taxonomique mondiale iNaturalist.

Ce module gère :
- Téléchargement de la BDD mondiale (~200 MB)
- Recherche locale ultra-rapide (~1ms par taxon)
- Mise à jour en arrière-plan
- Comparaison des versions
- Fallback vers API si taxon absent

Architecture :
- inat_taxonomy_active.db : BDD en cours d'utilisation
- inat_taxonomy_backup.db : Backup de l'ancienne version
- metadata.json : Métadonnées des versions
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple


class TaxonomyDatabase:
    """
    Gestionnaire de la base de données taxonomique mondiale iNaturalist.
    
    Permet la recherche locale ultra-rapide de la taxonomie complète
    pour ~1.5M de taxons, sans requête API.
    """
    
    # URLs de téléchargement (à adapter selon votre hébergement)
    DOWNLOAD_URL = "https://github.com/your-repo/releases/latest/inat_taxonomy_world.db.zip"
    CHECKSUM_URL = "https://github.com/your-repo/releases/latest/inat_taxonomy_world.sha256"
    
    # Configuration
    DATABASE_FILENAME = "inat_taxonomy_active.db"
    BACKUP_FILENAME = "inat_taxonomy_backup.db"
    METADATA_FILENAME = "metadata.json"
    
    def __init__(self, plugin_dir: str):
        """
        Initialise le gestionnaire de BDD taxonomique.
        
        Args:
            plugin_dir: Répertoire du plugin
        """
        self.plugin_dir = Path(plugin_dir)
        self.cache_dir = self.plugin_dir / "iNaturalist_Taxonomy_Cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.db_path = self.cache_dir / self.DATABASE_FILENAME
        self.backup_path = self.cache_dir / self.BACKUP_FILENAME
        self.metadata_path = self.cache_dir / self.METADATA_FILENAME
        
        self.connection = None
        self.cursor = None
    
    # ==========================================================================
    # CONNEXION ET INITIALISATION
    # ==========================================================================
    
    def connect(self) -> bool:
        """
        Se connecte à la base de données locale.
        
        Returns:
            bool: True si connexion réussie, False sinon
        """
        try:
            if not self.db_path.exists():
                return False
            
            self.connection = sqlite3.connect(str(self.db_path))
            self.cursor = self.connection.cursor()
            
            # Optimisations SQLite
            self.cursor.execute("PRAGMA journal_mode=WAL")
            self.cursor.execute("PRAGMA synchronous=NORMAL")
            self.cursor.execute("PRAGMA cache_size=-64000")  # 64 MB cache
            
            return True
            
        except Exception as e:
            print(f"Error connecting to database: {e}")
            return False
    
    def close(self):
        """Ferme la connexion à la base de données."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def is_installed(self) -> bool:
        """
        Vérifie si la base de données est installée.
        
        Returns:
            bool: True si installée, False sinon
        """
        return self.db_path.exists() and self.db_path.stat().st_size > 0
    
    # ==========================================================================
    # RECHERCHE DE TAXONOMIE
    # ==========================================================================
    
    def get_taxonomy(self, taxon_id: int) -> Optional[Dict]:
        """
        Récupère la taxonomie complète d'un taxon depuis la BDD locale.
        
        Args:
            taxon_id: ID du taxon iNaturalist
            
        Returns:
            dict ou None: {
                'taxon_id': int,
                'name': str,
                'rank': str,
                'kingdom': str,
                'phylum': str,
                'class': str,
                'order': str,
                'family': str,
                'genus': str,
                'species': str,
                'ancestor_ids': list
            }
        """
        if not self.connection:
            if not self.connect():
                return None
        
        try:
            self.cursor.execute("""
                SELECT taxon_id, name, rank, 
                       kingdom, phylum, class, "order", family, genus, species,
                       ancestor_ids
                FROM taxonomy
                WHERE taxon_id = ?
            """, (taxon_id,))
            
            row = self.cursor.fetchone()
            if not row:
                return None
            
            # Parser ancestor_ids (stocké en JSON)
            ancestor_ids = json.loads(row[10]) if row[10] else []
            
            return {
                'taxon_id': row[0],
                'name': row[1],
                'rank': row[2],
                'kingdom': row[3] or '',
                'phylum': row[4] or '',
                'class': row[5] or '',
                'order': row[6] or '',
                'family': row[7] or '',
                'genus': row[8] or '',
                'species': row[9] or '',
                'ancestor_ids': ancestor_ids
            }
            
        except Exception as e:
            print(f"Error fetching taxonomy for {taxon_id}: {e}")
            return None
    
    def get_batch_taxonomy(self, taxon_ids: List[int]) -> Dict[int, Dict]:
        """
        Récupère la taxonomie de plusieurs taxons en une seule requête.
        
        Args:
            taxon_ids: Liste d'IDs de taxons
            
        Returns:
            dict: {taxon_id: taxonomy_dict, ...}
        """
        if not self.connection:
            if not self.connect():
                return {}
        
        if not taxon_ids:
            return {}
        
        try:
            # Requête batch avec IN
            placeholders = ','.join('?' * len(taxon_ids))
            query = f"""
                SELECT taxon_id, name, rank,
                       kingdom, phylum, class, "order", family, genus, species,
                       ancestor_ids
                FROM taxonomy
                WHERE taxon_id IN ({placeholders})
            """
            
            self.cursor.execute(query, taxon_ids)
            
            results = {}
            for row in self.cursor.fetchall():
                ancestor_ids = json.loads(row[10]) if row[10] else []
                
                results[row[0]] = {
                    'taxon_id': row[0],
                    'name': row[1],
                    'rank': row[2],
                    'kingdom': row[3] or '',
                    'phylum': row[4] or '',
                    'class': row[5] or '',
                    'order': row[6] or '',
                    'family': row[7] or '',
                    'genus': row[8] or '',
                    'species': row[9] or '',
                    'ancestor_ids': ancestor_ids
                }
            
            return results
            
        except Exception as e:
            print(f"Error fetching batch taxonomy: {e}")
            return {}
    
    # ==========================================================================
    # MÉTADONNÉES ET STATISTIQUES
    # ==========================================================================
    
    def get_metadata(self) -> Dict:
        """
        Récupère les métadonnées de la base de données.
        
        Returns:
            dict: Métadonnées complètes
        """
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading metadata: {e}")
        
        # Métadonnées par défaut
        return {
            'active_database': None,
            'backup_database': None,
            'download_in_progress': None,
            'update_settings': {
                'auto_check': True,
                'check_frequency_days': 30,
                'last_check': None
            }
        }
    
    def save_metadata(self, metadata: Dict):
        """
        Sauvegarde les métadonnées.
        
        Args:
            metadata: Dictionnaire de métadonnées
        """
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata: {e}")
    
    def get_statistics(self) -> Dict:
        """
        Récupère les statistiques de la base de données.
        
        Returns:
            dict: {
                'total_taxa': int,
                'size_mb': float,
                'version': str,
                'install_date': str,
                'age_days': int,
                'status': str  # 'fresh', 'aging', 'old', 'very_old'
            }
        """
        if not self.is_installed():
            return {
                'total_taxa': 0,
                'size_mb': 0,
                'version': None,
                'install_date': None,
                'age_days': None,
                'status': 'not_installed'
            }
        
        # Récupérer métadonnées
        metadata = self.get_metadata()
        active_db = metadata.get('active_database') or metadata.get('databases', {}).get('active')
        
        # Compter les taxons
        total_taxa = 0
        if self.connect():
            try:
                self.cursor.execute("SELECT COUNT(*) FROM taxonomy")
                total_taxa = self.cursor.fetchone()[0]
            except Exception:
                pass
        
        # Taille du fichier
        size_mb = self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
        
        # Âge de la base
        install_date_str = active_db.get('install_date') if active_db else None
        version = active_db.get('version') if active_db else 'unknown'
        age_days = None
        status = 'unknown'
        
        if install_date_str:
            try:
                install_date = datetime.fromisoformat(install_date_str)
                age_days = (datetime.now() - install_date).days
                
                # Déterminer le statut
                if age_days < 90:
                    status = 'fresh'
                elif age_days < 180:
                    status = 'aging'
                elif age_days < 365:
                    status = 'old'
                else:
                    status = 'very_old'
            except Exception:
                pass
        
        return {
            'total_taxa': total_taxa,
            'size_mb': round(size_mb, 2),
            'version': version,
            'install_date': install_date_str,
            'age_days': age_days,
            'status': status
        }
    
    def get_status_emoji(self) -> Tuple[str, str]:
        """
        Retourne un emoji et un label pour le statut de la BDD.
        
        Returns:
            tuple: (emoji, label)
        """
        stats = self.get_statistics()
        status = stats['status']
        
        status_map = {
            'not_installed': ('⚫', 'Not Installed'),
            'fresh': ('🟢', 'Fresh'),
            'aging': ('🟡', 'Aging'),
            'old': ('🟠', 'Old'),
            'very_old': ('🔴', 'Very Old'),
            'unknown': ('⚪', 'Unknown')
        }
        
        return status_map.get(status, ('⚪', 'Unknown'))
    
    # ==========================================================================
    # GESTION DES VERSIONS
    # ==========================================================================
    
    def needs_update(self, check_frequency_days: int = 30) -> bool:
        """
        Vérifie si une mise à jour est recommandée.
        
        Args:
            check_frequency_days: Fréquence de vérification recommandée
            
        Returns:
            bool: True si mise à jour recommandée
        """
        stats = self.get_statistics()
        
        # Pas installée
        if stats['status'] == 'not_installed':
            return True
        
        # Très vieille (> 1 an)
        if stats['status'] == 'very_old':
            return True
        
        # Vérifier la dernière vérification
        metadata = self.get_metadata()
        last_check = metadata.get('update_settings', {}).get('last_check')
        
        if last_check:
            try:
                last_check_date = datetime.fromisoformat(last_check)
                days_since_check = (datetime.now() - last_check_date).days
                
                if days_since_check >= check_frequency_days:
                    return True
            except Exception:
                pass
        
        return False
    
    # ==========================================================================
    # CONTEXTE MANAGER
    # ==========================================================================
    
    def __enter__(self):
        """Support du context manager."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support du context manager."""
        self.close()

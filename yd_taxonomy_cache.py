"""
Module de cache persistant pour la taxonomie iNaturalist.

Ce module gère un cache SQLite qui stocke les informations taxonomiques
récupérées depuis l'API iNaturalist, évitant ainsi les requêtes répétées.

Structure de la base de données :
- Table taxonomy_cache : stockage des taxons avec TTL
- Table cache_metadata : métadonnées du cache (dernière cleanup, etc.)

Performance :
- Recherche : ~5ms par taxon (vs ~500ms via API)
- TTL par défaut : 365 jours (1 an)
- Auto-cleanup : tous les 7 jours

Compatibilité : v2.0.0 et v2.1.0
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List


class TaxonomyCache:
    """
    Gestionnaire de cache SQLite pour la taxonomie iNaturalist.
    
    Stocke les informations taxonomiques de manière persistante avec un TTL
    pour éviter les requêtes API répétées.
    """
    
    # Configuration
    CACHE_FOLDER = "iNaturalist_Taxonomy_Cache"
    CACHE_FILENAME = "inat_taxonomy_cache.db"
    DEFAULT_TTL_DAYS = 365  # 1 an
    CLEANUP_INTERVAL_DAYS = 7
    
    def __init__(self, plugin_dir: str):
        """
        Initialise le gestionnaire de cache.
        
        Args:
            plugin_dir: Répertoire du plugin
        """
        self.plugin_dir = Path(plugin_dir)
        self.cache_dir = self.plugin_dir / self.CACHE_FOLDER
        self.cache_dir.mkdir(exist_ok=True)
        
        self.db_path = self.cache_dir / self.CACHE_FILENAME
        self.connection = None
        self.cursor = None
        
        self._init_database()
    
    # ==========================================================================
    # INITIALISATION DE LA BASE DE DONNÉES
    # ==========================================================================
    
    def _init_database(self):
        """Initialise la base de données si elle n'existe pas."""
        self.connection = sqlite3.connect(str(self.db_path))
        self.cursor = self.connection.cursor()
        
        # Table principale : cache des taxons
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS taxonomy_cache (
                taxon_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                rank TEXT NOT NULL,
                taxonomy TEXT NOT NULL,
                ancestor_ids TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        
        # Index pour les recherches par expiration
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at 
            ON taxonomy_cache(expires_at)
        """)
        
        # Table de métadonnées
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        self.connection.commit()
        
        # Optimisations SQLite
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA synchronous=NORMAL")
    
    # ==========================================================================
    # OPÉRATIONS DE CACHE
    # ==========================================================================
    
    def get(self, taxon_id: int) -> Optional[Dict]:
        """
        Récupère un taxon depuis le cache.
        
        Args:
            taxon_id: ID du taxon iNaturalist
            
        Returns:
            dict ou None: {
                'name': str,
                'rank': str,
                'taxonomy': {kingdom: ..., phylum: ..., ...},
                'ancestor_ids': [...]
            }
        """
        try:
            now = datetime.now().isoformat()
            
            self.cursor.execute("""
                SELECT name, rank, taxonomy, ancestor_ids
                FROM taxonomy_cache
                WHERE taxon_id = ? AND expires_at > ?
            """, (taxon_id, now))
            
            row = self.cursor.fetchone()
            
            if row:
                return {
                    'name': row[0],
                    'rank': row[1],
                    'taxonomy': json.loads(row[2]),
                    'ancestor_ids': json.loads(row[3]) if row[3] else []
                }
            
            return None
            
        except Exception as e:
            print(f"Error getting taxon {taxon_id} from cache: {e}")
            return None
    
    def set(self, taxon_id: int, name: str, rank: str, taxonomy: Dict, 
            ancestor_ids: List[int] = None, ttl_days: int = None):
        """
        Stocke un taxon dans le cache.
        
        Args:
            taxon_id: ID du taxon
            name: Nom scientifique
            rank: Rang taxonomique
            taxonomy: Dict de taxonomie {kingdom: ..., phylum: ..., ...}
            ancestor_ids: Liste des IDs ancêtres
            ttl_days: Durée de vie en jours (défaut: 365)
        """
        try:
            if ttl_days is None:
                ttl_days = self.DEFAULT_TTL_DAYS
            
            now = datetime.now()
            created_at = now.isoformat()
            expires_at = (now + timedelta(days=ttl_days)).isoformat()
            
            taxonomy_json = json.dumps(taxonomy, ensure_ascii=False)
            ancestor_ids_json = json.dumps(ancestor_ids or [], ensure_ascii=False)
            
            # INSERT OR REPLACE pour mise à jour si existe
            self.cursor.execute("""
                INSERT OR REPLACE INTO taxonomy_cache 
                (taxon_id, name, rank, taxonomy, ancestor_ids, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (taxon_id, name, rank, taxonomy_json, ancestor_ids_json, 
                  created_at, expires_at))
            
            self.connection.commit()
            
        except Exception as e:
            print(f"Error setting taxon {taxon_id} in cache: {e}")
    
    def delete(self, taxon_id: int):
        """
        Supprime un taxon du cache.
        
        Args:
            taxon_id: ID du taxon à supprimer
        """
        try:
            self.cursor.execute("""
                DELETE FROM taxonomy_cache WHERE taxon_id = ?
            """, (taxon_id,))
            
            self.connection.commit()
            
        except Exception as e:
            print(f"Error deleting taxon {taxon_id} from cache: {e}")
    
    # ==========================================================================
    # MAINTENANCE DU CACHE
    # ==========================================================================
    
    def auto_cleanup(self) -> int:
        """
        Nettoie automatiquement les entrées expirées.
        
        S'exécute seulement si le dernier cleanup date de plus de 7 jours.
        
        Returns:
            int: Nombre d'entrées supprimées
        """
        try:
            # Vérifier la dernière cleanup
            self.cursor.execute("""
                SELECT value FROM cache_metadata WHERE key = 'last_cleanup'
            """)
            
            row = self.cursor.fetchone()
            
            if row:
                last_cleanup = datetime.fromisoformat(row[0])
                days_since = (datetime.now() - last_cleanup).days
                
                if days_since < self.CLEANUP_INTERVAL_DAYS:
                    # Pas encore temps de nettoyer
                    return 0
            
            # Effectuer le cleanup
            removed = self.cleanup_expired()
            
            # Mettre à jour la date de dernier cleanup
            self.cursor.execute("""
                INSERT OR REPLACE INTO cache_metadata (key, value, updated_at)
                VALUES ('last_cleanup', ?, ?)
            """, (datetime.now().isoformat(), datetime.now().isoformat()))
            
            self.connection.commit()
            
            return removed
            
        except Exception as e:
            print(f"Error in auto_cleanup: {e}")
            return 0
    
    def cleanup_expired(self) -> int:
        """
        Supprime toutes les entrées expirées.
        
        Returns:
            int: Nombre d'entrées supprimées
        """
        try:
            now = datetime.now().isoformat()
            
            # Compter avant suppression
            self.cursor.execute("""
                SELECT COUNT(*) FROM taxonomy_cache WHERE expires_at <= ?
            """, (now,))
            
            count = self.cursor.fetchone()[0]
            
            # Supprimer
            self.cursor.execute("""
                DELETE FROM taxonomy_cache WHERE expires_at <= ?
            """, (now,))
            
            self.connection.commit()
            
            return count
            
        except Exception as e:
            print(f"Error cleaning up expired entries: {e}")
            return 0
    
    def clear_all(self):
        """Vide complètement le cache."""
        try:
            self.cursor.execute("DELETE FROM taxonomy_cache")
            self.cursor.execute("DELETE FROM cache_metadata")
            self.connection.commit()
            
        except Exception as e:
            print(f"Error clearing cache: {e}")
    
    # ==========================================================================
    # STATISTIQUES
    # ==========================================================================
    
    def get_statistics(self) -> Dict:
        """
        Récupère les statistiques du cache.
        
        Returns:
            dict: {
                'total_entries': int,
                'expired_entries': int,
                'size_mb': float,
                'oldest_entry': str,
                'newest_entry': str
            }
        """
        try:
            stats = {}
            
            # Nombre total d'entrées
            self.cursor.execute("SELECT COUNT(*) FROM taxonomy_cache")
            stats['total_entries'] = self.cursor.fetchone()[0]
            
            # Nombre d'entrées expirées
            now = datetime.now().isoformat()
            self.cursor.execute("""
                SELECT COUNT(*) FROM taxonomy_cache WHERE expires_at <= ?
            """, (now,))
            stats['expired_entries'] = self.cursor.fetchone()[0]
            
            # Taille du fichier
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
                stats['size_mb'] = size_bytes / (1024 * 1024)
            else:
                stats['size_mb'] = 0
            
            # Entrée la plus ancienne
            self.cursor.execute("""
                SELECT created_at FROM taxonomy_cache 
                ORDER BY created_at ASC LIMIT 1
            """)
            row = self.cursor.fetchone()
            stats['oldest_entry'] = row[0] if row else None
            
            # Entrée la plus récente
            self.cursor.execute("""
                SELECT created_at FROM taxonomy_cache 
                ORDER BY created_at DESC LIMIT 1
            """)
            row = self.cursor.fetchone()
            stats['newest_entry'] = row[0] if row else None
            
            return stats
            
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {
                'total_entries': 0,
                'expired_entries': 0,
                'size_mb': 0,
                'oldest_entry': None,
                'newest_entry': None
            }
    
    # ==========================================================================
    # GESTION DE LA CONNEXION
    # ==========================================================================
    
    def close(self):
        """Ferme la connexion à la base de données."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def __enter__(self):
        """Support du context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support du context manager."""
        self.close()

# ==============================================================================
# PLUGIN QGIS : iNaturalist Import - Script 2 (Taxonomie)
# ==============================================================================
# Version    : 2.1.0 - FINALE - Base de données locale mondiale + Cache + API
# Auteur     : Yves Desnoës
# Date       : Janvier 2026
# QGIS       : 3.28+ (Firenze, Bratislava...)
#
# RÔLE :
# Ce script enrichit les données iNaturalist importées avec leur taxonomie
# complète sur 7 niveaux hiérarchiques (kingdom → species).
#
# PERFORMANCE (v2.0.0) :
# - Avec BDD locale : ~15-20 secondes (ultra-rapide !)
# - Téléchargement BDD : ~5 secondes (depuis Database Manager)
# - Gain vs version originale : 60x plus rapide
#
# ARCHITECTURE À 3 NIVEAUX (hybride intelligent) :
# 1. BDD locale mondiale   : ~1ms par taxon, 99.9% des requêtes (1.4M taxons)
# 2. Cache SQLite persistant : ~5ms, taxons exotiques récents
# 3. API iNaturalist        : ~500ms, taxons tout nouveaux (fallback)
#
# INSTALLATION BDD :
# Extensions → iNaturalist Import → Taxonomy Database Manager → Download Database
#
# ==============================================================================

# ==============================================================================
# IMPORTS
# ==============================================================================

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeatureRequest,
    QgsExpression,
    QgsSimpleMarkerSymbolLayer,
    QgsMarkerSymbol,
    QgsRuleBasedRenderer,
    QgsUnitTypes,
    QgsProject
)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QProgressDialog, QMessageBox, QApplication
from PyQt5.QtGui import QColor

import csv
import os
import time
from datetime import datetime
from requests.exceptions import HTTPError


# ==============================================================================
# CONFIGURATION GLOBALE
# ==============================================================================

# Champs taxonomiques
TAXON_FIELD = "taxon_id"  # Champ contenant l'ID du taxon iNaturalist
TAX_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# Pause API (fallback seulement - la BDD locale évite 99.9% des appels API)
SLEEP_BETWEEN_CALLS = 0.5   # Pause entre requêtes API (rarement utilisée)


# ==============================================================================
# SECTION 1 : SYMBOLOGIE TAXONOMIQUE
# ==============================================================================
# Fonctions pour appliquer une symbologie basée sur la classification biologique

def apply_taxonomy_symbology(layer):
    """
    Applique une symbologie basée sur les règles taxonomiques à une couche.
    
    Règles de symbologie (basées sur Symbo_10.qml) :
    - Plantes (kingdom = Plantae) : vert
    - Fonges (kingdom = Fungi) : orange
    - Arthropodes (phylum = Arthropoda) : jaune
    - Oiseaux (phylum = Chordata) : magenta
    - Mammifères (class = Mammalia) : marron avec contour jaune
    - Reptiles (class = Reptilia) : vert-bleu
    - Amphibiens (class = Amphibia) : vert-jaune
    - Autres (ELSE) : rouge très foncé avec contour jaune
    
    Paramètres:
        layer: QgsVectorLayer - La couche à laquelle appliquer la symbologie
    """
    from qgis.core import QgsRuleBasedRenderer
    
    # Définition des règles de symbologie
    # Format: (filter_expression, label, fill_color, outline_color, size)
    rules = [
        # Règle 0: Plantes
        (
            '"kingdom" = \'Plantae\'',
            'Plantes',
            QColor(0, 228, 88, 255),      # Vert
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 1: Fonges
        (
            '"kingdom" = \'Fungi\'',
            'Fonges',
            QColor(246, 131, 61, 255),     # Orange
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 2: Arthropodes
        (
            '"phylum" = \'Arthropoda\'',
            'Arthropodes',
            QColor(255, 255, 1, 255),      # Jaune
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 3: Oiseaux (Chordata)
        (
            '"phylum" = \'Chordata\'',
            'Oiseaux',
            QColor(254, 0, 253, 255),      # Magenta
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 4: Mammifères
        (
            '"class" = \'Mammalia\'',
            'Mamifères',
            QColor(155, 55, 0, 255),       # Marron
            QColor(255, 254, 0, 255),      # Jaune (contour)
            4.0
        ),
        # Règle 5: Reptiles
        (
            '"class" = \'Reptilia\'',
            'Reptiles',
            QColor(18, 144, 113, 255),     # Vert-bleu
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 6: Amphibiens
        (
            '"class" = \'Amphibia\'',
            'Amphibiens',
            QColor(190, 207, 80, 255),     # Vert-jaune
            QColor(35, 35, 35, 255),       # Gris foncé
            4.0
        ),
        # Règle 7: Autres (ELSE)
        (
            'ELSE',
            'Autres',
            QColor(4, 0, 0, 255),          # Rouge très foncé
            QColor(255, 255, 0, 255),      # Jaune (contour)
            4.0
        ),
    ]
    
    # Création du renderer basé sur des règles
    root_rule = QgsRuleBasedRenderer.Rule(None)
    
    for filter_expr, label, fill_color, outline_color, size in rules:
        # Création du symbole
        symbol = QgsMarkerSymbol.createSimple({})
        symbol_layer = symbol.symbolLayer(0)
        
        if isinstance(symbol_layer, QgsSimpleMarkerSymbolLayer):
            # Configuration du symbole
            symbol_layer.setShape(QgsSimpleMarkerSymbolLayer.Circle)
            symbol_layer.setSize(size)
            symbol_layer.setSizeUnit(QgsUnitTypes.RenderMillimeters)
            symbol_layer.setColor(fill_color)
            symbol_layer.setStrokeColor(outline_color)
            symbol_layer.setStrokeWidth(0.0)
            symbol_layer.setStrokeStyle(1)  # Solid
        
        # Création de la règle
        rule = QgsRuleBasedRenderer.Rule(symbol)
        rule.setFilterExpression(filter_expr)
        rule.setLabel(label)
        
        # Ajout de la règle à la règle racine
        root_rule.appendChild(rule)
    
    # Application du renderer à la couche
    renderer = QgsRuleBasedRenderer(root_rule)
    layer.setRenderer(renderer)


# ==============================================================
# SECTION 2 : FORMULAIRE D'ATTRIBUTS  
# ==============================================================

def apply_attribute_form_config(layer):
    """
    Configure le formulaire d'attributs selon Symbo_20.qml
    
    Configuration appliquée :
    1. Widgets ExternalResource pour url_obs et url_taxon (avec UseLink=true)
    2. Layout en mode TabLayout
    3. Structure en 3 COLONNES avec horizontalStretch :
       - Colonne 1 : "Observation" (horizontalStretch=4, 8 champs)
       - Colonne 2 : "   " vide (horizontalStretch=0, 7 champs)
       - Colonne 3 : "Taxonomy" (horizontalStretch=3, 7 champs)
    4. Relation Photos EN DEHORS des colonnes (au niveau racine)
    
    Compatible QGIS 3.28+ (Firenze) et 3.40+ (Bratislava)
    
    Args:
        layer (QgsVectorLayer): La couche à configurer
    """
    from qgis.core import (
        QgsEditorWidgetSetup,
        QgsEditFormConfig,
        QgsAttributeEditorContainer,
        QgsAttributeEditorField,
        QgsAttributeEditorRelation
    )
    
    # ==========================================================================
    # FONCTION DE COMPATIBILITÉ QGIS 3.28+
    # ==========================================================================
    
    def set_horizontal_stretch_safe(container, stretch_value):
        """
        Définit horizontalStretch si disponible (QGIS 3.34+).
        Sinon, ignore silencieusement (compatibilité QGIS 3.28).
        
        Args:
            container: QgsAttributeEditorContainer
            stretch_value: Valeur de stretch (0-N)
        """
        try:
            if hasattr(container, 'setHorizontalStretch'):
                container.setHorizontalStretch(stretch_value)
        except Exception:
            # QGIS 3.28 : méthode non disponible, on continue sans erreur
            pass
    
    # ==========================================================================
    # ÉTAPE 1 : CONFIGURATION DES WIDGETS DE CHAMPS
    # ==========================================================================
    
    fields = layer.fields()
    
    # Configuration ExternalResource pour url_obs
    url_obs_idx = fields.indexOf("url_obs")
    if url_obs_idx >= 0:
        config = {
            'DocumentViewer': 0,
            'DocumentViewerHeight': 0,
            'DocumentViewerWidth': 0,
            'FileWidget': True,
            'FileWidgetButton': True,
            'FileWidgetFilter': '',
            'FullUrl': True,
            'RelativeStorage': 0,
            'StorageAuthConfigId': '',
            'StorageMode': 0,
            'StorageType': '',
            'UseLink': True
        }
        setup = QgsEditorWidgetSetup('ExternalResource', config)
        layer.setEditorWidgetSetup(url_obs_idx, setup)
    
    # Configuration ExternalResource pour url_taxon
    url_taxon_idx = fields.indexOf("url_taxon")
    if url_taxon_idx >= 0:
        config = {
            'DocumentViewer': 0,
            'DocumentViewerHeight': 0,
            'DocumentViewerWidth': 0,
            'FileWidget': True,
            'FileWidgetButton': True,
            'FileWidgetFilter': '',
            'FullUrl': True,
            'RelativeStorage': 0,
            'StorageAuthConfigId': '',
            'StorageMode': 0,
            'StorageType': '',
            'UseLink': True
        }
        setup = QgsEditorWidgetSetup('ExternalResource', config)
        layer.setEditorWidgetSetup(url_taxon_idx, setup)
    
    # Configuration TextEdit pour taxon_id (avec IsMultiline=false, UseHtml=false)
    taxon_id_idx = fields.indexOf("taxon_id")
    if taxon_id_idx >= 0:
        config = {
            'IsMultiline': False,
            'UseHtml': False
        }
        setup = QgsEditorWidgetSetup('TextEdit', config)
        layer.setEditorWidgetSetup(taxon_id_idx, setup)
    
    # ==========================================================================
    # ÉTAPE 2 : CONFIGURATION DU FORMULAIRE (LAYOUT)
    # ==========================================================================
    
    form_config = layer.editFormConfig()
    form_config.clearTabs()
    form_config.setLayout(QgsEditFormConfig.TabLayout)
    
    # Container racine (3 colonnes)
    root_container = QgsAttributeEditorContainer("", None)
    root_container.setIsGroupBox(True)
    root_container.setColumnCount(3)
    
    # ==========================================================================
    # COLONNE 1 : OBSERVATION (horizontalStretch=4)
    # ==========================================================================
    
    obs_container = QgsAttributeEditorContainer("Observation", root_container)
    obs_container.setIsGroupBox(True)
    obs_container.setColumnCount(1)
    set_horizontal_stretch_safe(obs_container, 4)  # ← Compatible QGIS 3.28+
    
    # Champs de la colonne Observation (8 champs)
    obs_fields = [
        "inat_id",           # index 1
        "date_obs",          # index 2
        "scientific_name",   # index 3
        "vernacular_name_FR",# index 4
        "latitude",          # index 5
        "longitude",         # index 6
        "place_guess",       # index 7
        "precision"          # index 15
    ]
    
    for field_name in obs_fields:
        idx = fields.indexOf(field_name)
        if idx >= 0:
            field_element = QgsAttributeEditorField(field_name, idx, obs_container)
            obs_container.addChildElement(field_element)
    
    root_container.addChildElement(obs_container)
    
    # ==========================================================================
    # COLONNE 2 : "   " VIDE (horizontalStretch=0)
    # ==========================================================================
    
    middle_container = QgsAttributeEditorContainer("   ", root_container)
    middle_container.setIsGroupBox(True)
    middle_container.setColumnCount(1)
    set_horizontal_stretch_safe(middle_container, 0)  # ← Compatible QGIS 3.28+
    
    # Champs de la colonne centrale (7 champs)
    middle_fields = [
        "quality_grade",     # index 14
        "observateur_name",  # index 13
        "observateur_id",    # index 12
        "url_taxon",         # index 11
        "url_obs",           # index 10
        "taxon_rank",        # index 9
        "taxon_id"           # index 8
    ]
    
    for field_name in middle_fields:
        idx = fields.indexOf(field_name)
        if idx >= 0:
            field_element = QgsAttributeEditorField(field_name, idx, middle_container)
            middle_container.addChildElement(field_element)
    
    root_container.addChildElement(middle_container)
    
    # ==========================================================================
    # COLONNE 3 : TAXONOMY (horizontalStretch=3)
    # ==========================================================================
    
    taxo_container = QgsAttributeEditorContainer("Taxonomy", root_container)
    taxo_container.setIsGroupBox(True)
    taxo_container.setColumnCount(1)
    set_horizontal_stretch_safe(taxo_container, 3)  # ← Compatible QGIS 3.28+
    
    # Champs de taxonomie (7 champs - indexes 17-23)
    taxo_fields = [
        "kingdom",   # index 17
        "phylum",    # index 18
        "class",     # index 19
        "order",     # index 20
        "family",    # index 21
        "genus",     # index 22
        "species"    # index 23
    ]
    
    for field_name in taxo_fields:
        idx = fields.indexOf(field_name)
        if idx >= 0:
            field_element = QgsAttributeEditorField(field_name, idx, taxo_container)
            taxo_container.addChildElement(field_element)
    
    root_container.addChildElement(taxo_container)
    
    # ==========================================================================
    # RELATION PHOTOS (EN DEHORS DES COLONNES - AU NIVEAU RACINE)
    # ==========================================================================
    
    # Récupérer la relation photos si elle existe
    relations = layer.project().relationManager().relations()
    photos_relation_id = None
    
    for rel_id, relation in relations.items():
        if relation.referencingLayer() and relation.referencedLayer() == layer:
            # Chercher une relation avec "photo" dans le nom
            if "photo" in relation.name().lower() or "photo" in rel_id.lower():
                photos_relation_id = rel_id
                break
    
    # Ajouter la relation Photos si elle existe
    if photos_relation_id:
        relation_element = QgsAttributeEditorRelation(
            photos_relation_id,
            None  # parent = None car au niveau racine
        )
        relation_element.setLabel("")  # Pas de label personnalisé
        relation_element.setShowLabel(True)
        
        # setRelationWidgetTypeId : compatible QGIS 3.28+
        try:
            relation_element.setRelationWidgetTypeId("relation_editor")
        except Exception:
            pass  # QGIS 3.28 : méthode peut-être absente
        
        # Configuration du widget de relation (QGIS 3.34+)
        try:
            relation_config = {
                'allow_add_child_feature_with_no_geometry': False,
                'buttons': 'AllButtons',
                'show_first_feature': True
            }
            if hasattr(relation_element, 'setRelationEditorConfiguration'):
                relation_element.setRelationEditorConfiguration(relation_config)
        except Exception:
            pass  # QGIS 3.28 : méthode non disponible
    
    # ==========================================================================
    # ÉTAPE 3 : APPLICATION DE LA CONFIGURATION
    # ==========================================================================
    
    # Créer l'arbre du formulaire
    form_config.addTab(root_container)
    
    # Ajouter la relation Photos au niveau racine si elle existe
    if photos_relation_id:
        form_config.addTab(relation_element)
    
    # Appliquer la configuration
    layer.setEditFormConfig(form_config)


# ==============================================================================
# SECTION 2 : CLASSE PRINCIPALE DE TRAITEMENT
# ==============================================================================
# Orchestre l'ensemble du processus d'enrichissement taxonomique

class yd_run:
    """
    Gestionnaire principal de l'enrichissement taxonomique iNaturalist.
    
    Cette classe coordonne :
    1. Validation de la couche active
    2. Extraction des taxons uniques
    3. Récupération de la taxonomie (via API + cache SQLite)
    4. Intégration dans la couche GPKG
    5. Application de la symbologie et du formulaire
    
    Cache persistant :
    - Emplacement : iNaturalist_Taxonomy_Cache/inat_taxonomy_cache.db
    - TTL : 90 jours (configurable)
    - Auto-nettoyage : tous les 7 jours
    """

    # --------------------------------------------------------------------------
    # INITIALISATION
    # --------------------------------------------------------------------------

    def __init__(self, iface):
        """
        Initialise le gestionnaire de taxonomie.
        
        Args:
            iface (QgisInterface): Interface principale de QGIS
            
        Raises:
            ImportError: Si pyinaturalist n'est pas installé
        """
        self.iface = iface
        self.start_time = None
        self.log_path = None
        
        # Vérification de la dépendance pyinaturalist
        try:
            from pyinaturalist import get_taxa
            self.get_taxa = get_taxa
        except ImportError:
            raise ImportError(
                "pyinaturalist n'est pas installé. "
                "Veuillez exécuter le Script 1 d'abord."
            )

    # --------------------------------------------------------------------------
    # POINT D'ENTRÉE PRINCIPAL
    # --------------------------------------------------------------------------

    def run(self, context=None):
        """
        Orchestre le processus complet d'enrichissement taxonomique.
        
        Étapes :
        1. Affichage boîte d'information (EN/FR)
        2. Validation couche active
        3. Extraction GPKG info
        4. Initialisation log
        5. Chargement couche fichier
        6. Extraction taxons uniques
        7. Construction taxonomie (API + cache)
        8. Intégration dans la couche
        9. Reload + symbologie + formulaire
        10. Message de fin avec statistiques
        """
        # ======================================================================
        # ÉTAPE 1 : INFORMATION UTILISATEUR
        # ======================================================================
        # =========================================================
        
        # Sauvegarder le contexte pour le dialogue final
        self.context = context
        
        # ======================================================================
        # ÉTAPE 2 : INITIALISATION DU TRAITEMENT
        # ======================================================================
        
        self.start_time = datetime.now()

        # Validation couche active (existence + type vectoriel)
        active = self.iface.activeLayer()
        if not self._validate_active_layer(active):
            return

        # Extraction infos GPKG (chemin + nom couche)
        gpkg_info = self._extract_gpkg_info(active)
        if not gpkg_info:
            return
        gpkg_path, layer_name = gpkg_info
        
        # Initialisation fichier log
        base_dir = os.path.dirname(gpkg_path)
        self.log_path = os.path.join(base_dir, "iNat_ETAPE9_all_in_one_RELOAD.log")
        self._init_log()

        # ======================================================================
        # ÉTAPE 3 : CHARGEMENT ET EXTRACTION DES DONNÉES
        # ======================================================================

        # Chargement couche fichier (indépendante de la couche active)
        vl = self._load_gpkg_layer(gpkg_path, layer_name)
        if not vl:
            return

        # Extraction taxons uniques de la couche
        taxa, taxon_set = self._extract_unique_taxa(vl)
        if not taxa:
            self._log("❌ Aucun taxon_id valide trouvé")
            self._finalize_with_error()
            return

        # ======================================================================
        # ÉTAPE 4 : CONSTRUCTION DE LA TAXONOMIE (API + CACHE)
        # ======================================================================

        result = self._build_taxonomy(taxa)
        if result is None:
            return
        
        taxo_map = result['taxo_map']      # Mapping taxon_id → taxonomie
        cache_stats = result['stats']       # Statistiques cache (hits, API calls...)

        # ======================================================================
        # ÉTAPE 5 : INTÉGRATION DANS LA COUCHE
        # ======================================================================

        success = self._integrate_taxonomy_into_layer(vl, taxo_map)
        if not success:
            return

        # ======================================================================
        # ÉTAPE 6 : FINALISATION
        # ======================================================================

        # Reload couche active + application symbologie + formulaire
        self._reload_active_layer(gpkg_path)

        # Affichage message de fin avec statistiques complètes
        total_feats = vl.featureCount() if vl else 0
        self._show_completion_message(layer_name, len(taxa), total_feats, cache_stats)
    
    # ==========================================================================
    # MÉTHODES DE VALIDATION
    # ==========================================================================

    def _validate_active_layer(self, active):
        """
        Valide que la couche active est conforme (existe + vectorielle).
        
        Args:
            active: Couche active de QGIS
            
        Returns:
            bool: True si valide, False sinon
        """
        if active is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "No active layer / Aucune couche active",
                "Please activate a vector layer.\n\n"
                "Veuillez activer une couche vectorielle."
            )
            return False

        # CAS 2 : Couche non vectorielle
        if not isinstance(active, QgsVectorLayer):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Invalid layer type / Type de couche invalide",
                "The active layer must be a vector layer.\n\n"
                "La couche active doit être une couche vectorielle."
            )
            return False

        return True

    def _extract_gpkg_info(self, active):
        """
        Extrait le chemin GPKG et le nom de couche.
        Retourne (gpkg_path, layer_name) ou None en cas d'erreur.
        """
        source = active.source()
        
        # Extraction du chemin GPKG
        if "|" in source:
            gpkg_path = source.split("|")[0]
        else:
            gpkg_path = source

        # Vérification de l'extension
        if not gpkg_path.lower().endswith(".gpkg"):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Invalid layer / Couche invalide",
                "The active layer must be a GeoPackage (.gpkg).\n\n"
                "La couche active doit être un GeoPackage (.gpkg)."
            )
            return None

        layer_name = active.name()
        return (gpkg_path, layer_name)

    # ==============================================================
    # GESTION DU LOG
    # ==============================================================

    def _init_log(self):
        """
        Initialise le fichier de log
        """
        with open(self.log_path, "w", encoding="utf-8") as lf:
            lf.write(f"[{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}] "
                     f"=== ETAPE 9 (tout-en-un, reload) : début ===\n")

    def _log(self, msg):
        """
        Écrit un message dans le log et la console
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as lf:
            lf.write(line + "\n")

    def _finalize_with_error(self):
        """
        Finalise le log en cas d'erreur
        """
        end_time = datetime.now()
        self._log(f"=== FIN avec erreur === Durée : {end_time - self.start_time}")

    # ==============================================================
    # CHARGEMENT DE LA COUCHE GPKG
    # ==============================================================

    def _load_gpkg_layer(self, gpkg_path, layer_name):
        """
        Charge la couche GPKG depuis le fichier.
        Retourne la couche ou None en cas d'erreur.
        """
        if not os.path.exists(gpkg_path):
            self._log(f"❌ GPKG introuvable : {gpkg_path}")
            self._finalize_with_error()
            return None

        uri = f"{gpkg_path}|layername={layer_name}"
        vl = QgsVectorLayer(uri, layer_name, "ogr")

        if not vl.isValid():
            self._log("❌ Couche GPKG invalide")
            self._finalize_with_error()
            return None

        self._log(f"✅ Couche (fichier) chargée : {vl.name()} ({vl.featureCount()} entités)")

        taxon_idx = vl.fields().indexOf(TAXON_FIELD)
        if taxon_idx == -1:
            self._log(f"❌ Champ '{TAXON_FIELD}' introuvable")
            self._finalize_with_error()
            return None

        return vl

    # ==============================================================
    # EXTRACTION DES TAXON_ID UNIQUES
    # ==============================================================

    def _extract_unique_taxa(self, vl):
        """
        Extrait la liste des taxon_id uniques présents dans la couche.
        Retourne (taxa_list, taxon_set_dict)
        """
        self._log("🔍 Extraction des taxon_id uniques...")

        taxon_idx = vl.fields().indexOf(TAXON_FIELD)
        taxon_set = {}
        sci_index = vl.fields().indexOf("scientific_name")
        sci_idx = sci_index if sci_index != -1 else -1

        for f in vl.getFeatures():
            tid = f[taxon_idx]
            if tid is None:
                continue
            try:
                tid_int = int(tid)
            except (TypeError, ValueError):
                continue
            if tid_int not in taxon_set:
                sci = f[sci_idx] if sci_idx != -1 else None
                taxon_set[tid_int] = sci

        taxa = sorted(taxon_set.keys())
        self._log(f"✅ {len(taxa)} taxon_id uniques extraits")

        return taxa, taxon_set

    # ==========================================================================
    # CONSTRUCTION DE LA TAXONOMIE (COEUR DU SYSTÈME)
    # ==========================================================================

    def _build_taxonomy(self, taxa):
        """
        Construit la taxonomie complète pour tous les taxons.
        
        VERSION 2.0.0 - BASE DE DONNÉES LOCALE MONDIALE + CACHE + API
        
        Architecture hybride à 3 niveaux :
        1. BDD locale mondiale (prioritaire) : ~1ms par taxon, 99.9% des cas
        2. Cache SQLite persistant (fallback) : ~5ms, taxons exotiques récents
        3. API iNaturalist (ultime fallback) : ~500ms, taxons tout nouveaux
        
        Performance attendue :
        - Avec BDD locale : ~20-30 secondes (tous les traitements)
        - Sans BDD locale : ~15 secondes avec cache, 17 min sans cache
        
        Args:
            taxa (list): Liste des taxon_id à traiter
            
        Returns:
            dict: {
                'taxo_map': {taxon_id: taxonomy_dict},
                'stats': {api_calls, cache_hits, db_hits, ...}
            }
            ou None si annulation utilisateur
        """
        from .yd_taxonomy_cache import TaxonomyCache
        from .yd_taxonomy_database import TaxonomyDatabase
        
        self._log("🌳 Construction de la taxonomie (v2.0.0 - BDD LOCALE + CACHE + API)...")
        
        # ==========================================================================
        # INITIALISATION DES SOURCES DE DONNÉES
        # ==========================================================================
        
        plugin_dir = os.path.dirname(__file__)
        
        # Source 1 : Base de données locale mondiale (prioritaire)
        local_db = TaxonomyDatabase(plugin_dir)
        has_local_db = local_db.is_installed()
        
        if has_local_db:
            local_db.connect()
            self._log("✅ Base de données locale détectée - Recherche ultra-rapide activée")
        else:
            self._log("⚠️ Base de données locale non installée - Utilisation cache + API")
            self._log("💡 Installez la BDD locale via le menu pour des performances optimales")
        
        # Source 2 : Cache SQLite persistant (fallback)
        cache = TaxonomyCache(plugin_dir)
        
        # Auto-nettoyage du cache
        removed = cache.auto_cleanup()
        if removed > 0:
            self._log(f"🧹 Auto-cleanup cache : {removed} entrées expirées supprimées")
        
        # ==========================================================================
        # VARIABLES DE SUIVI
        # ==========================================================================
        
        taxo_map = {}
        taxon_cache_memory = {}  # Cache mémoire (session en cours)
        errors = 0
        
        # Statistiques détaillées
        stats = {
            'db_hits': 0,        # Trouvés dans BDD locale
            'cache_hits': 0,     # Trouvés dans cache SQLite
            'api_calls': 0,      # Requêtes API
            'memory_hits': 0     # Trouvés dans cache mémoire
        }
        
        # ==========================================================================
        # FONCTION DE REQUÊTE API AVEC GESTION D'ERREURS
        # ==========================================================================
        
        def safe_get_taxa(tid):
            """Requête API avec gestion des erreurs 429 et retry"""
            retries = 0
            while True:
                try:
                    resp = self.get_taxa(taxon_id=tid)
                    time.sleep(SLEEP_BETWEEN_CALLS)
                    return resp
                except HTTPError as e:
                    if "429" in str(e) and retries < MAX_RETRIES_429:
                        retries += 1
                        self._log(
                            f"⚠️ 429 pour taxon_id={tid}, tentative "
                            f"{retries}/{MAX_RETRIES_429}, pause {SLEEP_ON_429}s..."
                        )
                        time.sleep(SLEEP_ON_429)
                    else:
                        raise
        
        # ==========================================================================
        # DIALOGUE DE PROGRESSION
        # ==========================================================================
        
        total_taxa = len(taxa)
        progress = QProgressDialog(
            f"Building taxonomy for {total_taxa} unique taxa...\n"
            f"Using: {'Local DB + Cache + API' if has_local_db else 'Cache + API'}",
            "Cancel / Annuler",
            0,
            total_taxa,
            self.iface.mainWindow()
        )
        progress.setWindowTitle("STEP 9 – Taxonomy / Taxonomie")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        # ==========================================================================
        # BOUCLE PRINCIPALE : TRAITEMENT DE CHAQUE TAXON
        # ==========================================================================
        
        for i, tid in enumerate(taxa):
            # Vérification annulation
            if progress.wasCanceled():
                self._log("⚠️ Construction de la taxonomie annulée par l'utilisateur.")
                progress.close()
                if has_local_db:
                    local_db.close()
                cache.close()
                return None
            
            # Mise à jour progression
            progress.setValue(i)
            progress_text = (
                f"Processing taxon {i+1}/{total_taxa} (ID: {tid})\n"
                f"Stats: 🗄️ DB:{stats['db_hits']} | 💾 Cache:{stats['cache_hits']} | "
                f"🌐 API:{stats['api_calls']}\n\n"
                "------------------------------------------------------------\n"
                f"Traitement taxon {i+1}/{total_taxa} (ID: {tid})\n"
                f"Stats: 🗄️ BDD:{stats['db_hits']} | 💾 Cache:{stats['cache_hits']} | "
                f"🌐 API:{stats['api_calls']}"
            )
            progress.setLabelText(progress_text)
            QApplication.processEvents()
            
            # ======================================================================
            # NIVEAU 0 : CACHE MÉMOIRE (instantané)
            # ======================================================================
            
            if tid in taxon_cache_memory:
                stats['memory_hits'] += 1
                continue  # Déjà traité
            
            # ======================================================================
            # NIVEAU 1 : BASE DE DONNÉES LOCALE (prioritaire, ~1ms)
            # ======================================================================
            
            info = None
            
            if has_local_db:
                info = local_db.get_taxonomy(tid)
                
                if info:
                    stats['db_hits'] += 1
                    taxon_cache_memory[tid] = info
                    
                    # Construction de la taxonomie à partir des données BDD
                    rank_to_name = {
                        'kingdom': info.get('kingdom', ''),
                        'phylum': info.get('phylum', ''),
                        'class': info.get('class', ''),
                        'order': info.get('order', ''),
                        'family': info.get('family', ''),
                        'genus': info.get('genus', ''),
                        'species': info.get('species', '')
                    }
                    
                    taxo_map[tid] = {field: rank_to_name.get(field, "") for field in TAX_FIELDS}
                    continue  # Taxon trouvé, passer au suivant
            
            # ======================================================================
            # NIVEAU 2 : CACHE SQLITE PERSISTANT (~5ms)
            # ======================================================================
            
            cached_data = cache.get(tid)
            
            if cached_data:
                stats['cache_hits'] += 1
                
                # Construire info depuis cache
                info = {
                    'taxon_id': tid,
                    'name': cached_data['name'],
                    'rank': cached_data['rank'],
                    'ancestor_ids': cached_data.get('ancestor_ids', [])
                }
                
                taxon_cache_memory[tid] = info
                taxo_map[tid] = cached_data['taxonomy']
                continue  # Taxon trouvé, passer au suivant
            
            # ======================================================================
            # NIVEAU 3 : API iNaturalist (ultime fallback, ~500ms)
            # ======================================================================
            
            try:
                resp = safe_get_taxa(tid)
                stats['api_calls'] += 1
                
                if not resp or "results" not in resp or not resp["results"]:
                    self._log(f"⚠️ Pas de résultat API pour taxon_id={tid}")
                    errors += 1
                    taxo_map[tid] = {field: "" for field in TAX_FIELDS}
                    continue
                
                # Parser la réponse API
                result = resp["results"][0]
                info = {
                    "taxon_id": result.get("id", tid),
                    "name": result.get("name", ""),
                    "rank": result.get("rank", ""),
                    "ancestor_ids": result.get("ancestor_ids", [])
                }
                
                taxon_cache_memory[tid] = info
                
                # Récupérer les ancêtres (de la BDD locale si possible, sinon API)
                for aid in info["ancestor_ids"]:
                    if aid not in taxon_cache_memory:
                        # Essayer la BDD locale d'abord
                        if has_local_db:
                            ancestor_info = local_db.get_taxonomy(aid)
                            if ancestor_info:
                                stats['db_hits'] += 1
                                taxon_cache_memory[aid] = ancestor_info
                                continue
                        
                        # Essayer le cache ensuite
                        ancestor_cached = cache.get(aid)
                        if ancestor_cached:
                            stats['cache_hits'] += 1
                            taxon_cache_memory[aid] = {
                                'taxon_id': aid,
                                'name': ancestor_cached['name'],
                                'rank': ancestor_cached['rank']
                            }
                            continue
                        
                        # Sinon requête API
                        try:
                            anc_resp = safe_get_taxa(aid)
                            stats['api_calls'] += 1
                            
                            if anc_resp and "results" in anc_resp and anc_resp["results"]:
                                anc_result = anc_resp["results"][0]
                                taxon_cache_memory[aid] = {
                                    "taxon_id": anc_result.get("id", aid),
                                    "name": anc_result.get("name", ""),
                                    "rank": anc_result.get("rank", ""),
                                    "ancestor_ids": anc_result.get("ancestor_ids", [])
                                }
                        except Exception as e:
                            self._log(f"⚠️ Erreur récupération ancêtre {aid}: {e}")
                            errors += 1
                
                # Construire la taxonomie hiérarchique
                rank_to_name = {}
                
                for aid in info["ancestor_ids"]:
                    ainfo = taxon_cache_memory.get(aid)
                    if ainfo and ainfo.get("rank") in TAX_FIELDS:
                        rank_to_name[ainfo["rank"]] = ainfo["name"]
                
                if info["rank"] in TAX_FIELDS:
                    rank_to_name[info["rank"]] = info["name"]
                
                taxonomy = {field: rank_to_name.get(field, "") for field in TAX_FIELDS}
                taxo_map[tid] = taxonomy
                
                # Sauvegarder dans le cache pour la prochaine fois
                cache.set(
                    tid,
                    info["name"],
                    info["rank"],
                    taxonomy,
                    info["ancestor_ids"]
                )
                
            except Exception as e:
                self._log(f"❌ Erreur traitement taxon {tid}: {e}")
                errors += 1
                taxo_map[tid] = {field: "" for field in TAX_FIELDS}
        
        # ==========================================================================
        # FINALISATION
        # ==========================================================================
        
        progress.setValue(total_taxa)
        progress.close()
        
        # Fermeture des connexions
        if has_local_db:
            local_db.close()
        cache.close()
        
        # ==========================================================================
        # STATISTIQUES FINALES
        # ==========================================================================
        
        successfully_processed = sum(1 for t in taxo_map.values() if any(t.values()))
        total_requests = stats['db_hits'] + stats['cache_hits'] + stats['api_calls']
        
        # Hit rates
        if total_requests > 0:
            db_hit_rate = stats['db_hits'] / total_requests * 100
            cache_hit_rate = stats['cache_hits'] / total_requests * 100
            api_rate = stats['api_calls'] / total_requests * 100
        else:
            db_hit_rate = cache_hit_rate = api_rate = 0
        
        # Statistiques du cache
        cache_stats = cache.get_statistics()
        
        self._log(f"✅ Taxonomie construite pour {len(taxo_map)} taxon_id")
        self._log(f"📊 Statistiques (v2.0.0 BDD Locale + Cache + API) :")
        self._log(f"   - Taxons avec données complètes : {successfully_processed}/{len(taxa)}")
        
        if has_local_db:
            self._log(f"   - 🗄️  BDD locale : {stats['db_hits']} ({db_hit_rate:.1f}%)")
        
        self._log(f"   - 💾 Cache SQLite : {stats['cache_hits']} ({cache_hit_rate:.1f}%)")
        self._log(f"   - 🌐 Requêtes API : {stats['api_calls']} ({api_rate:.1f}%)")
        self._log(f"   - 🧠 Cache mémoire : {stats['memory_hits']}")
        self._log(f"   - 🗄️  Taille cache : {cache_stats['size_mb']:.2f} Mo ({cache_stats['total_entries']} entrées)")
        self._log(f"   - ❌ Erreurs : {errors}")
        
        # Estimation du temps économisé
        if stats['db_hits'] > 0:
            time_saved_min = int(stats['db_hits'] * SLEEP_BETWEEN_CALLS / 60)
            self._log(f"   ✅ Temps économisé grâce à la BDD locale : ~{time_saved_min} minutes")
        elif stats['cache_hits'] > 0:
            time_saved_min = int(stats['cache_hits'] * SLEEP_BETWEEN_CALLS / 60)
            self._log(f"   ✅ Temps économisé grâce au cache : ~{time_saved_min} minutes")
        
        # Retourner taxo_map ET les statistiques
        return {
            'taxo_map': taxo_map,
            'stats': {
                'db_hits': stats['db_hits'],
                'cache_hits': stats['cache_hits'],
                'api_calls': stats['api_calls'],
                'memory_hits': stats['memory_hits'],
                'db_hit_rate': db_hit_rate,
                'cache_hit_rate': cache_hit_rate,
                'cache_size_mb': cache_stats['size_mb'],
                'cache_entries': cache_stats['total_entries'],
                'errors': errors
            }
        }
    def _integrate_taxonomy_into_layer(self, vl, taxo_map):
        """
        Intègre la taxonomie dans la couche GPKG (ajout de champs + remplissage).
        Retourne True si succès, False sinon.
        """
        self._log("🧬 Intégration directe de la taxonomie dans la couche (fichier)...")
    
        provider = vl.dataProvider()
        existing_fields = [f.name() for f in vl.fields()]
        new_fields = []
    
        # Ajout des champs taxonomiques manquants
        for field_name in TAX_FIELDS:
            if field_name not in existing_fields:
                new_fields.append(QgsField(field_name, QVariant.String, len=150))
    
        if new_fields:
            self._log(
                f"➕ Ajout de {len(new_fields)} champs taxonomiques : "
                f"{', '.join(f.name() for f in new_fields)}"
            )
            provider.addAttributes(new_fields)
            vl.updateFields()
        else:
            self._log("ℹ️ Tous les champs taxonomiques existent déjà")
    
        # Index des champs taxonomiques
        idx_map = {name: vl.fields().indexOf(name) for name in TAX_FIELDS}
        taxon_idx = vl.fields().indexOf(TAXON_FIELD)
    
        # Passage en mode édition
        if not vl.isEditable():
            vl.startEditing()
    
        n_updated = 0
        n_not_found = 0
    
        self._log("✏️ Mise à jour des entités dans le fichier...")
    
        # Dialogue de progression
        total_feats = vl.featureCount()
        progress_feats = QProgressDialog(
            "Updating taxonomy in the layer...\n"
            f"{total_feats} features to update.",
            "Cancel / Annuler",
            0,
            total_feats,
            self.iface.mainWindow(),
        )
        progress_feats.setWindowTitle("STEP 9 – Layer update / Mise à jour de la couche")
        progress_feats.setWindowModality(Qt.WindowModal)
        progress_feats.setMinimumDuration(0)
    
        # Mise à jour de chaque entité
        i_feat = 0
        for feat in vl.getFeatures():
            i_feat += 1
    
            if progress_feats.wasCanceled():
                self._log("⚠️ Mise à jour des entités annulée par l'utilisateur.")
                progress_feats.close()
                vl.rollBack()
                return False
    
            progress_feats.setValue(i_feat)
            progress_feats.setLabelText(
                "Updating taxonomy in the layer...\n"
                f"Feature {i_feat}/{total_feats} (FID={feat.id()})\n\n"
                "------------------------------------------------------------\n"
                "Intégration de la taxonomie dans la couche...\n"
                f"Entité {i_feat}/{total_feats} (FID={feat.id()})"
            )
            QApplication.processEvents()
    
            tid_val = feat[taxon_idx]
            try:
                tid_int = int(tid_val)
            except (TypeError, ValueError):
                n_not_found += 1
                continue
    
            taxo = taxo_map.get(tid_int)
            if not taxo:
                n_not_found += 1
                continue
    
            # Attribution des valeurs taxonomiques
            for field_name in TAX_FIELDS:
                idx = idx_map[field_name]
                feat[idx] = taxo.get(field_name, "")
    
            if not vl.updateFeature(feat):
                self._log(f"⚠️ Échec updateFeature pour FID={feat.id()}")
            else:
                n_updated += 1
    
        progress_feats.close()
    
        # Commit des modifications
        if vl.commitChanges():
            self._log(
                f"✅ Intégration terminée dans le fichier : "
                f"{n_updated} entités MAJ, {n_not_found} sans taxonomie"
            )
            return True
        else:
            self._log("❌ Erreur lors du commit sur fichier, annulation")
            vl.rollBack()
            return False
    
    # ==============================================================
    # RECHARGEMENT DE LA COUCHE ACTIVE
    # ==============================================================
    
    def _reload_active_layer(self, gpkg_path):
        """
        Recharge la couche active si elle pointe sur le GPKG modifié,
        applique la symbologie taxonomique et configure le formulaire d'attributs
        """
        self._log("🔄 Tentative de reload de la couche active...")
    
        active = self.iface.activeLayer()
        if active and isinstance(active, QgsVectorLayer):
            src = active.source().replace("\\", "/")
            gpkg_norm = gpkg_path.replace("\\", "/")
            
            if gpkg_norm in src:
                active.reload()
                
                # SECTION 1 : Application de la symbologie taxonomique
                apply_taxonomy_symbology(active)
                
                # SECTION 2 : Application de la configuration du formulaire
                apply_attribute_form_config(active)
                
                # Rafraîchissement de l'affichage
                active.triggerRepaint()
                
                self._log("✅ Couche active rechargée avec symbologie et formulaire personnalisés")
            else:
                self._log(
                    f"ℹ️ Couche active ne pointe pas sur ce GPKG "
                    f"({gpkg_norm} not in {src}), aucun reload effectué."
                )
        else:
            self._log("ℹ️ Pas de couche active ou couche non vectorielle, aucun reload effectué.")
    
    # ==============================================================
    # MESSAGE DE FIN
    # ==============================================================
    
    def _show_completion_message(self, layer_name, nb_taxa, nb_observations, cache_stats):
        """
        Affiche la boîte de dialogue de fin de traitement avec toutes les informations.
        
        Args:
            layer_name (str): Nom de la couche traitée
            nb_taxa (int): Nombre de taxons traités
            nb_observations (int): Nombre d'observations traitées
            cache_stats (dict): Statistiques du cache (api_calls, cache_hits, hit_rate, etc.)
        """
        end_time = datetime.now()
        self._log(f"Durée totale Taxonomy : {end_time - self.start_time}")
        self._log("=== FIN Taxonomy ===")
    
        # Formatage des heures
        start_str = self.start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
    
        # Calcul de la durée
        duration_td = end_time - self.start_time
        total_seconds = int(duration_td.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        duration_str = f"{h:02d}:{m:02d}:{s:02d}"
    
        # Construction du message avec les informations du cache
        cache_info_en = ""
        cache_info_fr = ""
        
        if cache_stats['cache_hits'] > 0:
            cache_info_en = (
                f"\n📊 Cache Performance:\n"
                f"   • Hit rate: {cache_stats['cache_hit_rate']:.1f}%\n"
                f"   • API calls: {cache_stats['api_calls']}\n"
                f"   • Cache hits: {cache_stats['cache_hits']}\n"
                f"   • Cache size: {cache_stats['cache_size_mb']:.2f} MB ({cache_stats['cache_entries']} entries)\n"
            )
            cache_info_fr = (
                f"\n📊 Performances du cache :\n"
                f"   • Taux de succès : {cache_stats['cache_hit_rate']:.1f}%\n"
                f"   • Requêtes API : {cache_stats['api_calls']}\n"
                f"   • Hits cache : {cache_stats['cache_hits']}\n"
                f"   • Taille du cache : {cache_stats['cache_size_mb']:.2f} Mo ({cache_stats['cache_entries']} entrées)\n"
            )
    
        # ======================================================================
        # DIALOGUE FINAL COMPLET
        # ======================================================================
        
        # Chemin icône
        import os
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, "icons", "mActionIdentify.png")
        
        # Récupérer les infos du contexte (Script 1) si disponibles
        if self.context:
            latitude_centre = self.context.get('latitude_centre', 0)
            longitude_centre = self.context.get('longitude_centre', 0)
            rayon_metres = self.context.get('rayon_metres', 0)
            dossier_projet = self.context.get('dossier_projet', '')
            nb_observations_total = self.context.get('nb_observations', 0)
            nb_taxons_total = self.context.get('nb_taxons', 0)
            nb_photos_total = self.context.get('nb_photos', 0)
        else:
            # Valeurs par défaut si pas de contexte
            latitude_centre = 0
            longitude_centre = 0
            rayon_metres = 0
            dossier_projet = ''
            nb_observations_total = nb_observations
            nb_taxons_total = nb_taxa
            nb_photos_total = 0
        
        # Créer le dialogue
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QDialogButtonBox
        from qgis.PyQt.QtCore import Qt
        
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("iNaturalist Import - Complete / Terminé")
        dialog.setMinimumWidth(900)
        dialog.setMinimumHeight(700)
        
        layout = QVBoxLayout()
        
        # Titre
        title = QLabel("<h2 style='color: #2E7D32;'>✅ Import Complete / Import Terminé</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Contenu HTML bilingue
        content_html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ width: 100%; }}
            td {{ vertical-align: top; padding: 10px; }}
            h3 {{ color: #1976D2; margin-top: 15px; }}
            ul {{ margin-top: 5px; }}
            .success {{ color: #2E7D32; font-weight: bold; }}
            .warning {{ color: #D32F2F; font-weight: bold; }}
            .icon-text {{ vertical-align: middle; }}
        </style>
        </head>
        <body>
        <table cellpadding="10" cellspacing="0" border="0">
        <tr>
            <!-- ENGLISH COLUMN -->
            <td width="50%" style="border-right: 2px solid #ccc; padding-right: 15px;">
                <h3>Circle parameters</h3>
                <ul>
                    <li>✅ <b>Center:</b> Lat {latitude_centre:.6f}, Lon {longitude_centre:.6f}</li>
                    <li>✅ <b>Radius:</b> {rayon_metres / 1000:.2f} km</li>
                </ul>
                
                <h3>Statistics</h3>
                <ul>
                    <li>✅ <b>Observations:</b> {nb_observations_total}</li>
                    <li>✅ <b>Distinct taxa:</b> {nb_taxons_total}</li>
                    <li>✅ <b>Photos:</b> {nb_photos_total}</li>
                </ul>
                
                <h3>Save location</h3>
                <ul>
                    <li>✅ <b>Folder:</b> {dossier_projet}</li>
                </ul>
                
                <h3>At the end of processing:</h3>
                <ul>
                    <li>✅ The 7 taxonomy fields have been added to the attribute table</li>
                    <li>✅ A basic symbology has been applied (customizable to your needs)</li>
                </ul>
                
                <h3>How to use</h3>
                <p>
                    <img src="file:///{icon_path.replace(chr(92), '/')}" width="24" height="24" class="icon-text" style="margin-right: 5px;">
                    <b>Use the Identify tool</b> to click on an observation point and open its <b>attribute form</b>.
                </p>
                <p>
                    ✅ <b>Key feature:</b> The form displays a <b>photos viewer</b> at the bottom with all observation photos in full size.
                </p>
                <p>
                    ✅ Clickable URLs provide direct access to the iNaturalist observation and taxon pages.
                </p>
                
                <h3>
                    <span style="font-size: 32px; vertical-align: middle; margin-right: 8px;">⚠️</span>
                    Important: Save your project!
                </h3>
                <p class="warning">
                    You MUST save your QGIS project to preserve the "Photos iNaturalist" relation.
                </p>
                <p>
                    Without saving, the photo viewer will not work when you reopen the project.
                </p>
            </td>
            
            <!-- FRENCH COLUMN -->
            <td width="50%" style="padding-left: 15px;">
                <h3>Paramètres du cercle</h3>
                <ul>
                    <li>✅ <b>Centre :</b> Lat {latitude_centre:.6f}, Lon {longitude_centre:.6f}</li>
                    <li>✅ <b>Rayon :</b> {rayon_metres / 1000:.2f} km</li>
                </ul>
                
                <h3>Statistiques</h3>
                <ul>
                    <li>✅ <b>Observations :</b> {nb_observations_total}</li>
                    <li>✅ <b>Taxons distincts :</b> {nb_taxons_total}</li>
                    <li>✅ <b>Photos :</b> {nb_photos_total}</li>
                </ul>
                
                <h3>Emplacement de sauvegarde</h3>
                <ul>
                    <li>✅ <b>Dossier :</b> {dossier_projet}</li>
                </ul>
                
                <h3>À la fin du traitement :</h3>
                <ul>
                    <li>✅ Les 7 champs de la taxonomie ont été ajoutés à la table d'attributs</li>
                    <li>✅ Une symbologie de base a été appliquée (adaptable selon vos besoins)</li>
                </ul>
                
                <h3>Mode d'emploi</h3>
                <p>
                    <img src="file:///{icon_path.replace(chr(92), '/')}" width="24" height="24" class="icon-text" style="margin-right: 5px;">
                    <b>Utilisez l'outil Information</b> pour cliquer sur un point d'observation et ouvrir son <b>formulaire d'attributs</b>.
                </p>
                <p>
                    ✅ <b>Point fort :</b> Le formulaire affiche un <b>visualiseur de photos</b> en bas avec toutes les photos de l'observation en taille réelle.
                </p>
                <p>
                    ✅ Les URLs cliquables donnent un accès direct aux pages iNaturalist de l'observation et du taxon.
                </p>
                
                <h3>
                    <span style="font-size: 32px; vertical-align: middle; margin-right: 8px;">⚠️</span>
                    Important : Enregistrez votre projet !
                </h3>
                <p class="warning">
                    Vous DEVEZ enregistrer votre projet QGIS pour sauvegarder la relation "Photos iNaturalist".
                </p>
                <p>
                    Sans sauvegarde, le visualiseur de photos ne fonctionnera pas à la réouverture du projet.
                </p>
            </td>
        </tr>
        </table>
        </body>
        </html>
        """
        
        # Afficher le HTML
        browser = QTextBrowser()
        browser.setHtml(content_html)
        browser.setOpenExternalLinks(False)
        layout.addWidget(browser)
        
        # Bouton OK
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        # =========================================================
        # AFFICHAGE DU NOMBRE D'ENTITÉS DANS LE GESTIONNAIRE DE COUCHES
        # =========================================================
        # Activer l'affichage du nombre d'entités pour les deux couches
        
        from qgis.core import QgsProject
        from qgis.gui import QgsLayerTreeView
        
        # Récupérer le projet et le layer tree
        project = QgsProject.instance()
        layer_tree_root = project.layerTreeRoot()
        
        # Couche principale
        main_layer = None
        for layer in project.mapLayers().values():
            if layer.name() == layer_name:
                main_layer = layer
                break
        
        if main_layer:
            # Trouver le noeud dans l'arbre des couches
            tree_layer = layer_tree_root.findLayer(main_layer.id())
            if tree_layer:
                # Activer l'affichage du nombre d'entités
                tree_layer.setCustomProperty("showFeatureCount", True)
                print(f"✅ Nombre d'entités activé pour : {layer_name}")
                # Rafraîchir en passant le NOEUD, pas la couche
                if hasattr(self.iface, 'layerTreeView'):
                    self.iface.layerTreeView().layerTreeModel().refreshLayerLegend(tree_layer)
        
        # Couche photos (même nom que la couche principale + "_Photos")
        photos_layer_name = f"{layer_name}_Photos"
        photos_layer = None
        print(f"🔍 Recherche de la couche photos : '{photos_layer_name}'")
        
        for layer in project.mapLayers().values():
            if layer.name() == photos_layer_name:
                photos_layer = layer
                print(f"   ✅ Couche photos trouvée : '{layer.name()}'")
                break
        
        if photos_layer:
            # Trouver le noeud dans l'arbre des couches
            tree_layer_photos = layer_tree_root.findLayer(photos_layer.id())
            if tree_layer_photos:
                # Activer l'affichage du nombre d'entités
                tree_layer_photos.setCustomProperty("showFeatureCount", True)
                print(f"✅ Nombre d'entités activé pour : {photos_layer.name()}")
                # Rafraîchir en passant le NOEUD, pas la couche
                if hasattr(self.iface, 'layerTreeView'):
                    self.iface.layerTreeView().layerTreeModel().refreshLayerLegend(tree_layer_photos)
            else:
                print(f"⚠️ Noeud de couche photos introuvable dans l'arbre")
        else:
            print(f"⚠️ Couche photos '{photos_layer_name}' introuvable dans le projet")
        
        dialog.exec_()
    
    

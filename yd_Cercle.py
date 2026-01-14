# ==============================================================
# Plugin QGIS : iNaturalist Import v2.1.0
# Script     : yd_Cercle.py (sous-programme de yd_Script_1.py)
# Rôle       : Dessin interactif d'un cercle géodésique dans une couche vectorielle
#              et restitution des paramètres (centre, rayon, nom de couche)
# Méthode    : Cercle géodésique universel (compatible iNaturalist)
#              via SCR azimutal équidistant centré sur le point
# QGIS       : 3.40 (Bratislava)
# ==============================================================

# -*- coding: utf-8 -*-

import math
import os
import re

from qgis.PyQt.QtWidgets import QMessageBox, QInputDialog
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QVariant, pyqtSignal
from qgis.gui import QgsMapTool, QgsRubberBand

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsGeometryGeneratorSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsWkbTypes,
    QgsProject,
    QgsField,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorFileWriter,
    QgsDistanceArea,
)


class YD_Cercle(QgsMapTool):

    # ------------------------------------------------------------------
    # Signal de fin :
    # latitude_centre (EPSG:4326),
    # longitude_centre (EPSG:4326),
    # rayon (m),
    # nom de la couche cercle
    # ------------------------------------------------------------------
    finished = pyqtSignal(float, float, float, str)

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        super().__init__(self.canvas)

        self.center = None
        self.center_wgs84 = None  # Centre en coordonnées WGS84 (pour le SCR azimutal)
        self.rubber_band = None
        self.radius = None

        # Nom de la couche cercle (nouvelle donnée contractuelle)
        self.layer_name = None
        
        # Outil de calcul de distance géodésique
        self.distance_calc = QgsDistanceArea()
        self.distance_calc.setEllipsoid('WGS84')

    # ------------------------------------------------------------------
    # Initialisation de l'outil de dessin
    # ------------------------------------------------------------------

    def run(self):
        # Test si le projet QGIS est enregistré
        project = QgsProject.instance()
        
        if not project.fileName():
            message = """Your current QGIS project MUST be saved in a folder of your choice.
All output files created by this tool will be placed in THIS same folder.

Click OK to exit, save your project, then restart the program.

------------------------------------------------------------
Votre projet QGIS en cours DOIT être enregistré, dans un dossier de votre choix.
Tous les fichiers de sortie créés par cet outil seront placés dans CE même dossier.

Cliquez sur OK pour quitter, enregistrez votre projet, puis relancez le programme.
"""
            QMessageBox.warning(
                None,
                "iNaturalist Import - ATTENTION !",
                message
            )
            return
        
        QMessageBox.information(
            None,
            "Draw Circle / Dessiner un cercle\n",
            "Click and drag to define a circle,\n"
            "then click a second time to confirm.\n"
            "---------------------------------------------\n"
            "Faire un cliquer-glisser pour définir un cercle,\n"
            "puis cliquer une seconde fois pour le valider."
        )
        self.canvas.setMapTool(self)

    # ------------------------------------------------------------------
    # Gestion des clics souris
    # ------------------------------------------------------------------
    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())

        # Premier clic : définition du centre
        if self.center is None:
            self.center = point
            
            # Conversion immédiate du centre en WGS84 pour le SCR azimutal
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(
                canvas_crs,
                wgs84_crs,
                QgsProject.instance()
            )
            self.center_wgs84 = transform.transform(point)

            self.rubber_band = QgsRubberBand(
                self.canvas,
                QgsWkbTypes.PolygonGeometry
            )

            self.rubber_band.setColor(QColor(255, 255, 0))
            self.rubber_band.setFillColor(QColor(255, 255, 0, 60))
            self.rubber_band.setWidth(2)
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

        # Second clic : validation du rayon
        else:
            # Calcul du rayon GÉODÉSIQUE (distance réelle sur la sphère)
            # Convertir le point cliqué en WGS84
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(
                canvas_crs,
                wgs84_crs,
                QgsProject.instance()
            )
            point_wgs84 = transform.transform(point)
            
            # Calculer la distance géodésique en mètres
            self.radius = self.distance_calc.measureLine(
                self.center_wgs84,
                point_wgs84
            )

            rayon, ok = QInputDialog.getDouble(
                None,
                "Circle Radius / Rayon du cercle",
                "Radius (in meters) / Rayon (en mètres) :\n\n"
                "You can validate this value or enter a custom one.\n"
                "--------------------------------------------------\n"                
                "Vous pouvez valider cette valeur ou en saisir une autre.\n",
                self.radius,
                1.0,
                1_000_000.0,
                1
            )

            if ok:
                self._create_layer_and_circle(rayon)

                # ÉMISSION DU SIGNAL DE FIN
                # (incluant explicitement le nom de la couche cercle)
                self.finished.emit(
                    self.center_wgs84.y(),   # latitude
                    self.center_wgs84.x(),   # longitude
                    rayon,                   # rayon (m)
                    self.layer_name          # NOM DE LA COUCHE CERCLE
                )

            self._cleanup()

    # ------------------------------------------------------------------
    # Mise à jour dynamique du cercle
    # ------------------------------------------------------------------
    def canvasMoveEvent(self, event):
        if self.center is None or self.rubber_band is None:
            return

        point = self.toMapCoordinates(event.pos())
        
        # Convertir le point en WGS84
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(
            canvas_crs,
            wgs84_crs,
            QgsProject.instance()
        )
        point_wgs84 = transform.transform(point)
        
        # Calculer le rayon géodésique
        radius = self.distance_calc.measureLine(self.center_wgs84, point_wgs84)
        
        # Dessiner l'aperçu du cercle géodésique
        self._draw_circle_preview(radius)

    # ------------------------------------------------------------------
    # Dessin du cercle géodésique dynamique (aperçu en temps réel)
    # ------------------------------------------------------------------
    def _draw_circle_preview(self, radius_m, segments=32):
        """Aperçu géodésique du cercle pendant le dessin"""
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        
        # Créer un cercle géodésique temporaire
        geom = self._create_geodesic_circle(
            self.center_wgs84.x(),
            self.center_wgs84.y(),
            radius_m,
            segments  # Moins de segments pour l'aperçu (plus fluide)
        )
        
        # Reprojeter dans le SCR du canvas pour l'affichage
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        transform = QgsCoordinateTransform(
            wgs84_crs,
            canvas_crs,
            QgsProject.instance()
        )
        geom.transform(transform)
        
        # Dessiner le polygone dans le rubber band
        if geom.type() == QgsWkbTypes.PolygonGeometry:
            polygon = geom.asPolygon()
            if polygon:
                for point in polygon[0]:
                    self.rubber_band.addPoint(point, False)
                self.rubber_band.closePoints()

    # ------------------------------------------------------------------
    # Nettoyage de l'outil
    # ------------------------------------------------------------------
    def _cleanup(self):
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.rubber_band = None

        self.center = None
        self.center_wgs84 = None
        self.canvas.unsetMapTool(self)

    # ------------------------------------------------------------------
    # Création d'un cercle géodésique via SCR azimutal équidistant
    # ------------------------------------------------------------------
    def _create_geodesic_circle(self, center_lon, center_lat, radius_m, segments=64):
        """
        Crée un cercle géodésique exact (compatible iNaturalist)
        en utilisant un SCR azimutal équidistant centré sur le point.
        
        Args:
            center_lon: longitude du centre (EPSG:4326)
            center_lat: latitude du centre (EPSG:4326)
            radius_m: rayon en mètres
            segments: nombre de segments pour le polygone
            
        Returns:
            QgsGeometry: géométrie du cercle en EPSG:4326
        """
        # Créer un SCR azimutal équidistant centré sur le point
        proj_string = (
            f'+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} '
            f'+x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs'
        )
        aeqd_crs = QgsCoordinateReferenceSystem()
        aeqd_crs.createFromProj(proj_string)
        
        if not aeqd_crs.isValid():
            raise Exception("Erreur : SCR azimutal équidistant invalide")
        
        # Créer le point centre en WGS84
        wgs84_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        center_point = QgsPointXY(center_lon, center_lat)
        
        # Transformer vers le SCR azimutal
        transform_to_aeqd = QgsCoordinateTransform(
            wgs84_crs,
            aeqd_crs,
            QgsProject.instance()
        )
        center_aeqd = transform_to_aeqd.transform(center_point)
        
        # Créer le cercle (buffer) dans le SCR azimutal
        circle_geom = QgsGeometry.fromPointXY(center_aeqd).buffer(radius_m, segments)
        
        # Retransformer vers WGS84
        transform_to_wgs84 = QgsCoordinateTransform(
            aeqd_crs,
            wgs84_crs,
            QgsProject.instance()
        )
        circle_geom.transform(transform_to_wgs84)
        
        return circle_geom

    # ------------------------------------------------------------------
    # Création de la couche cercle + persistance GPKG
    # ------------------------------------------------------------------
    def _create_layer_and_circle(self, rayon):

        project = QgsProject.instance()
        project_file = project.fileName()
        if not project_file:
            raise Exception("Le projet QGIS doit être enregistré")

        project_dir = os.path.dirname(project_file)
        indices = set()

        for lyr in project.mapLayers().values():
            m = re.match(r"cercle_(\d+)$", lyr.name())
            if m:
                indices.add(int(m.group(1)))

        for fname in os.listdir(project_dir):
            m = re.match(r"cercle_(\d+)\.gpkg$", fname)
            if m:
                indices.add(int(m.group(1)))

        next_index = max(indices) + 1 if indices else 1
        layer_name = f"cercle_{next_index:02d}"

        # mémorisation du nom de couche (NOUVEAU, ESSENTIEL)
        self.layer_name = layer_name

        # Création couche mémoire en WGS84
        layer = QgsVectorLayer(
            "Polygon?crs=EPSG:4326",
            layer_name,
            "memory"
        )
        # IMPORTANT : addMapLayer(layer, False) = n'ajoute PAS au LayerTree
        # On l'ajoutera manuellement à la racine après
        QgsProject.instance().addMapLayer(layer, False)
        
        # Ajouter à la RACINE du LayerTree (pas dans un groupe)
        root = QgsProject.instance().layerTreeRoot()
        root.insertLayer(0, layer)  # Position 0 = racine, en haut
        
        provider = layer.dataProvider()

        # Création du cercle géodésique
        geom = self._create_geodesic_circle(
            self.center_wgs84.x(),
            self.center_wgs84.y(),
            rayon
        )

        # Définition des champs attributaires
        provider.addAttributes([
            QgsField("latitude_centre_(EPSG:4326)", QVariant.Double),
            QgsField("longitude_centre_(EPSG:4326)", QVariant.Double),
            QgsField("Rayon_(m)", QVariant.Double),
        ])
        layer.updateFields()

        feature = QgsFeature(layer.fields())
        feature.setGeometry(geom)

        feature.setAttributes([
            self.center_wgs84.y(),
            self.center_wgs84.x(),
            rayon
        ])

        provider.addFeature(feature)
        layer.updateExtents()

        # Stylisation ROBUSTE avec QColor explicite
        # (évite les problèmes d'interprétation entre versions QGIS)
        
        # Création du symbole de remplissage
        fill_symbol = QgsFillSymbol()
        
        # Configuration de la couche de symbole principale
        symbol_layer = fill_symbol.symbolLayer(0)
        
        # Couleur de remplissage : Magenta TOTALEMENT transparent
        fill_color = QColor(255, 0, 255, 0)  # RGBA explicite TOTALEMENT transparent
        symbol_layer.setFillColor(fill_color)
        
        # Couleur de contour : Rouge vif
        stroke_color = QColor(255, 0, 0, 255)  # RGBA explicite
        symbol_layer.setStrokeColor(stroke_color)
        symbol_layer.setStrokeWidth(1.0)
        
        # Marker au centroid
        marker = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": "255,0,255,255",  # Magenta opaque
            "size": "3"
        })

        gg_layer = QgsGeometryGeneratorSymbolLayer.create({
            "geometryModifier": "centroid($geometry)",
            "SymbolType": "Marker"
        })
        gg_layer.setSubSymbol(marker)
        fill_symbol.appendSymbolLayer(gg_layer)

        layer.setRenderer(QgsSingleSymbolRenderer(fill_symbol))
        layer.triggerRepaint()

        # Export GPKG
        gpkg_path = os.path.join(project_dir, f"{layer_name}.gpkg")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.fileEncoding = "UTF-8"

        result, error = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer,
            gpkg_path,
            project.transformContext(),
            options
        )
        if result != QgsVectorFileWriter.NoError:
            raise Exception(f"Erreur écriture GPKG : {error}")

        saved_renderer = layer.renderer().clone()

        gpkg_layer = QgsVectorLayer(
            f"{gpkg_path}|layername={layer_name}",
            layer_name,
            "ogr"
        )
        if not gpkg_layer.isValid():
            raise Exception("Couche GPKG invalide")

        gpkg_layer.setRenderer(saved_renderer)
        
        # IMPORTANT : addMapLayer(layer, False) = n'ajoute PAS au LayerTree
        QgsProject.instance().addMapLayer(gpkg_layer, False)
        
        # Ajouter à la RACINE du LayerTree (pas dans un groupe)
        root = QgsProject.instance().layerTreeRoot()
        root.insertLayer(0, gpkg_layer)  # Position 0 = racine, en haut
        
        # Supprimer la couche mémoire temporaire
        QgsProject.instance().removeMapLayer(layer.id())

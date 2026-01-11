# ==============================================================
# Plugin QGIS : iNaturalist Import
# Script     : yd_Cercle.py (sous-programme de yd_Script_1.py)
# Rôle       : Dessin interactif d’un cercle dans une couche vectorielle
#              et restitution des paramètres (centre, rayon, nom de couche)
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

        # --- FORÇAGE SCU PROJET EN EPSG:2154 ---
        project = QgsProject.instance()
        crs_2154 = QgsCoordinateReferenceSystem("EPSG:2154")

        if project.crs() != crs_2154:
            project.setCrs(crs_2154)

        self.canvas.setDestinationCrs(crs_2154)
        self.canvas.refresh()
        # -------------------------------------

        super().__init__(self.canvas)

        self.center = None
        self.rubber_band = None
        self.radius = None

        # Nom de la couche cercle (nouvelle donnée contractuelle)
        self.layer_name = None

    # ------------------------------------------------------------------
    # Initialisation de l’outil de dessin
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
            self.radius = self._distance(self.center, point)

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
                self._create_layer_and_circle(self.center, rayon)

                # Transformation du centre en EPSG:4326
                crs_src = QgsCoordinateReferenceSystem("EPSG:2154")
                crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
                transform = QgsCoordinateTransform(
                    crs_src,
                    crs_dest,
                    QgsProject.instance()
                )

                centre_4326 = transform.transform(self.center)

                # ÉMISSION DU SIGNAL DE FIN
                # (incluant explicitement le nom de la couche cercle)
                self.finished.emit(
                    centre_4326.y(),   # latitude
                    centre_4326.x(),   # longitude
                    rayon,             # rayon (m)
                    self.layer_name    # NOM DE LA COUCHE CERCLE
                )

            self._cleanup()

    # ------------------------------------------------------------------
    # Mise à jour dynamique du cercle
    # ------------------------------------------------------------------
    def canvasMoveEvent(self, event):
        if self.center is None or self.rubber_band is None:
            return

        point = self.toMapCoordinates(event.pos())
        radius = self._distance(self.center, point)
        self._draw_circle(self.center, radius)

    # ------------------------------------------------------------------
    # Dessin du cercle dynamique
    # ------------------------------------------------------------------
    def _draw_circle(self, center, radius, segments=64):
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            self.rubber_band.addPoint(QgsPointXY(x, y), False)

        self.rubber_band.closePoints()

    # ------------------------------------------------------------------
    # Calcul de distance cartésienne
    # ------------------------------------------------------------------
    def _distance(self, p1, p2):
        return math.hypot(p1.x() - p2.x(), p1.y() - p2.y())

    # ------------------------------------------------------------------
    # Nettoyage de l’outil
    # ------------------------------------------------------------------
    def _cleanup(self):
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.rubber_band = None

        self.center = None
        self.canvas.unsetMapTool(self)

    # ------------------------------------------------------------------
    # Création de la couche cercle + persistance GPKG
    # ------------------------------------------------------------------
    def _create_layer_and_circle(self, center, rayon):

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

        # Création couche mémoire
        layer = QgsVectorLayer(
            "Polygon?crs=EPSG:2154",
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

        # Géométrie
        points = []
        for i in range(64):
            angle = 2 * math.pi * i / 64
            x = center.x() + rayon * math.cos(angle)
            y = center.y() + rayon * math.sin(angle)
            points.append(QgsPointXY(x, y))
        points.append(points[0])

        geom = QgsGeometry.fromPolygonXY([points])

        provider.addAttributes([
            QgsField("x_centre_(EPSG:2154)", QVariant.Double),
            QgsField("y_centre_(EPSG:2154)", QVariant.Double),
            QgsField("Rayon_(m)", QVariant.Double),
            QgsField("latitude_centre_(EPSG:4326)", QVariant.Double),
            QgsField("longitude_centre_(EPSG:4326)", QVariant.Double),
        ])
        layer.updateFields()

        feature = QgsFeature(layer.fields())
        feature.setGeometry(geom)

        crs_src = QgsCoordinateReferenceSystem("EPSG:2154")
        crs_dest = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(
            crs_src,
            crs_dest,
            QgsProject.instance()
        )
        centre_4326 = transform.transform(center)

        feature.setAttributes([
            center.x(),
            center.y(),
            rayon,
            centre_4326.y(),
            centre_4326.x()
        ])

        provider.addFeature(feature)
        layer.updateExtents()

        # Stylisation ROBUSTE avec QColor explicite
        # (évite les problèmes d'interprétation entre versions QGIS)
        
        # Création du symbole de remplissage
        fill_symbol = QgsFillSymbol()
        
        # Configuration de la couche de symbole principale
        symbol_layer = fill_symbol.symbolLayer(0)
        
        # Couleur de remplissage : Magenta semi-transparent
        #fill_color = QColor(255, 0, 255, 60)  # RGBA explicite
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
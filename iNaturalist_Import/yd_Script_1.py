# ==============================================================
# Plugin QGIS : iNaturalist Import
# Script     : yd_Script_1
# Version    : 1.0.0
# Rôle       : Import de données iNaturalist depuis une zone circulaire
# Remarque   : Script original encapsulé pour usage plugin
# QGIS       : 3.40 (Bratislava)
# ==============================================================

# ==============================================================
# yd_Script_1_plugin.py
# Plugin-safe encapsulation of yd_Script_1_INITIAL.py
#
#*** NO INTERNAL MODIFICATION OF ORIGINAL CODE
#*** Original script is encapsulated verbatim
#*** Entry point for plugin: yd_run(iface)
# ==============================================================

from qgis.PyQt import QtWidgets

_yd_iface = None

def yd_run(iface):
    """Plugin entry point"""
    run_original_script(iface)

# ==============================================================
#*** ORIGINAL SCRIPT — UNCHANGED (ENCAPSULATED)
# ==============================================================

def run_original_script(iface):
 
    # ==============================================================
    # === CONTROLE DEPENDANCE pyinaturalist ========================
    # ==============================================================

    try:
        from pyinaturalist.node_api import get_observations
    except ImportError:
        QtWidgets.QMessageBox.critical(
            iface.mainWindow(),
            "iNaturalist Importation - ATTENTION ! Missing dependency",             
            "This tool requires the Python module 'pyinaturalist'.\n"
            "To install it for QGIS:\n\n"
            "1. Close QGIS.\n"
            "2. Open the 'OSGeo4W Shell' or the 'QGIS Python Console'.\n"
            "3. Run the following command:\n"
            "   python -m pip install pyinaturalist\n"
            "4. Restart QGIS.\n\n"
            "------------------------------------------------------------\n"
            "Cet outil nécessite le module Python 'pyinaturalist'.\n"
            "Pour l’installer dans QGIS :\n\n"
            "1. Fermez QGIS.\n"
            "2. Ouvrez le « OSGeo4W Shell » ou la « Console Python de QGIS ».\n"
            "3. Lancez la commande suivante :\n"
            "   python -m pip install pyinaturalist\n"
            "4. Redémarrez QGIS.\n"
        )
        return

    
    #*** GLOBAL SHARED VARIABLES (plugin encapsulation fix)
    global circle_result  #***
    global layer          #***
    global proj           #***
    global canvas         #***
    #*** END globals

    import os
    import importlib.util
    
    #from pyinaturalist.node_api import get_observations
    
    from qgis.core import (
        QgsProject, QgsWkbTypes, QgsFeature, QgsGeometry, QgsPointXY,
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDistanceArea,
        QgsVectorLayer, QgsVectorFileWriter,
        QgsFillSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer,
        QgsGeometryGeneratorSymbolLayer, QgsFields, QgsField, Qgis
    )
    from qgis.gui import QgsMapTool, QgsRubberBand
    from qgis.utils import iface
    from qgis.PyQt.QtCore import Qt, QVariant, QDateTime
    from qgis.PyQt.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QLineEdit, QComboBox,
        QDialogButtonBox, QRadioButton, QCheckBox, QInputDialog, QMessageBox
    )
    
   
    # ==============================================================
    # 2) MÉMORISATION SCR INITIAL + PROJET ENREGISTRÉ
    # ==============================================================
    
    proj = QgsProject.instance()
    canvas = iface.mapCanvas()
    
    initial_crs = proj.crs()
    print(f"[DEBUG] Initial project CRS: {initial_crs.authid()}")
    
    project_path = proj.readPath("./")
    
    msg_text = (
        "Your current QGIS project MUST be saved in a folder of your choice.\n"
        "All output files created by this tool will be placed in THIS same folder.\n\n"
        "If your project is not already saved, please save it now,\n"
        "then click OK to continue.\n\n"
        "------------------------------------------------------------\n"
        "Votre projet QGIS en cours DOIT être enregistré, dans un dossier de votre choix.\n"
        "Tous les fichiers de sortie créés par cet outil seront placés dans CE même dossier.\n\n"
        "Si votre projet n'est pas déjà enregistré, veuillez l'enregistrer maintenant,\n"
        "puis cliquez sur OK pour continuer.\n"
    )
    
    QMessageBox.information(
        iface.mainWindow(),
        "iNaturalist Import - ATTENTION !",
        msg_text
    )
    
    project_path = proj.readPath("./")
    print(f"[DEBUG] Project path after save check: {project_path}")
    
    # ==============================================================
    # 3) NOM DU CERCLE (cercle_XX.gpkg)
    # ==============================================================
    
    def next_circle_name_and_path():
        proj_local = QgsProject.instance()
        project_path_local = proj_local.readPath("./")
        base_name = "cercle"
        idx = 1
        while True:
            layer_name_local = f"{base_name}_{idx:02d}"
            gpkg_path_local = os.path.join(project_path_local, f"{layer_name_local}.gpkg")
            if not os.path.exists(gpkg_path_local):
                print(f"✅ Nom retenu : {layer_name_local} → fichier : {gpkg_path_local}")
                return layer_name_local, gpkg_path_local, project_path_local
            idx += 1
    
    layer_name, gpkg_path, project_path = next_circle_name_and_path()
    
    # ==============================================================
    # 4) VARIABLES GLOBALES (cercle → ETAPE 7)
    # ==============================================================
    
    circle_result = {"lat": None, "lon": None, "rayon_m": None}
    layer = None  # couche temporaire pour le cercle
    
    # ==============================================================
    # 5) ETAPE 7/8 : iNat à partir du cercle
    # ==============================================================
    
    def etape7_cercle_champs_et_photos():
        lat = circle_result["lat"]
        lng = circle_result["lon"]
        rayon_m = circle_result["rayon_m"]
    
        if lat is None or lng is None or rayon_m is None:
            print("❌ Aucun cercle défini (lat/lon/rayon_m manquants), arrêt ETAPE 7")
            return
    
        rayon_km = rayon_m / 1000.0
        print(f"📍 lat={lat}, lng={lng}, rayon={rayon_m} m ({rayon_km} km pour iNat)")
    
        # ---------- DIALOGUE 1 : FILTRES ----------
        dialog = QDialog()
        dialog.setWindowTitle("iNaturalist Import - Input Filters")
        dialog.resize(400, 280)
        layout = QVBoxLayout()
    
        layout.addWidget(QLabel("Date début (incluse) YYYY-MM-DD (vide = tout) :"))
        d1_edit = QLineEdit()
        layout.addWidget(d1_edit)
    
        layout.addWidget(QLabel("Date fin (exclue) YYYY-MM-DD (vide = tout) :"))
        d2_edit = QLineEdit()
        layout.addWidget(d2_edit)
    
        layout.addWidget(QLabel(
            "User login (empty = all) / Login utilisateur (vide = tous) :"
        ))
        user_combo = QComboBox()
        user_combo.setEditable(True)
        user_combo.addItem("")  # tous les utilisateurs
        layout.addWidget(user_combo)
    
        layout.addWidget(QLabel("Taxon nom scientifique (vide = tous) :"))
        taxon_combo = QComboBox()
        taxon_combo.setEditable(True)
        taxon_combo.addItem("")  # tous les taxons
        layout.addWidget(taxon_combo)
    
        layout.addWidget(QLabel("Quality grade :"))
        quality_combo = QComboBox()
        quality_combo.addItems(["tous", "research", "needs_id", "casual"])
        layout.addWidget(quality_combo)
    
        # ---------- Pré-scan des user_login et taxons (page 1) ----------
        presets_params = {
            'lat': lat,
            'lng': lng,
            'radius': rayon_km,
            'per_page': 200,
            'page': 1,
            'captive': False,
        }
        try:
            resp_preset = get_observations(**presets_params)
            results_preset = resp_preset.get('results', [])
        except Exception as e:
            print(f"⚠️ Impossible de précharger user_login/taxons : {e}")
            results_preset = []
    
        user_set = set()
        taxon_set = set()
        for obs in results_preset:
            user_obj = obs.get('user', {}) or {}
            login = user_obj.get('login')
            if login:
                user_set.add(login)
    
            taxon_obj = obs.get('taxon', {}) or {}
            sci_name = taxon_obj.get('name')
            if sci_name:
                taxon_set.add(sci_name)
    
        for login in sorted(user_set):
            user_combo.addItem(login)
        for sci_name in sorted(taxon_set):
            taxon_combo.addItem(sci_name)
    
        print(f"🔑 {len(user_set)} user_login trouvés dans le cercle (pré-scan).")
        print(f"🔬 {len(taxon_set)} taxons trouvés dans le cercle (pré-scan).")
    
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
    
        dialog.setLayout(layout)
        result = dialog.exec_()
        if result != QDialog.Accepted:
            print("❌ Annulé par utilisateur (filtres)")
            return
    
        d1_str = d1_edit.text()
        d2_str = d2_edit.text()
        user_login = user_combo.currentText()
        taxon_nom = taxon_combo.currentText()
        quality_grade = quality_combo.currentText()
    
        print(
            f"🔍 Filtres : {d1_str or 'tout'}→{d2_str or 'tout'} "
            f"user={user_login or 'tous'} taxon={taxon_nom or 'tous'} quality={quality_grade}"
        )
    
        # ---------- PAGINATION iNat ----------
        all_obs = []
        page = 1
    
        while True:
            params = {
                'lat': lat,
                'lng': lng,
                'radius': rayon_km,
                'per_page': 200,
                'page': page,
                'captive': False,
                'locale': 'fr',             # noms vernaculaires en français
                'preferred_place_id': 6753  # ex: France
            }
    
            if d1_str.strip():
                params['d1'] = d1_str.strip()
            if d2_str.strip():
                params['d2'] = d2_str.strip()
            if user_login.strip():
                params['user_login'] = user_login.strip()
            if taxon_nom.strip():
                params['taxon_name'] = taxon_nom.strip()
            if quality_grade == "research":
                params['quality_grade'] = "research"
            if quality_grade == "needs_id":
                params['quality_grade'] = "needs_id"
            if quality_grade == "casual":
                params['quality_grade'] = "casual"
    
            resp = get_observations(**params)
            results = resp.get('results', [])
            if not results:
                break
    
            all_obs.extend(results)
            page += 1
    
        print(f"{len(all_obs)} observations récupérées.")
        max_photos = max((len(obs.get('photos', [])) for obs in all_obs), default=0)
        print(f"Maximum {max_photos} photos.")
    
        # ---------- DIALOGUE 2 : CHAMPS + MODE PHOTOS ----------
        champs_dialog = QDialog()
        champs_dialog.setWindowTitle("iNaturalist Import - Output Filters")
        champs_dialog.resize(400, 540)
        champs_layout = QVBoxLayout()
    
        champs_layout.addWidget(QLabel("Non-photo fields to include :"))
    
        champs_checks = {
            "date_obs": QCheckBox("Date observation"),
            "scientific_name": QCheckBox("scientific_name"),
            "vernacular_name_FR": QCheckBox("Nom vernaculaire FR"),
            "latitude": QCheckBox("Latitude"),
            "longitude": QCheckBox("Longitude"),
            "place_guess": QCheckBox("lieu_iNat"),
            "taxon_rank": QCheckBox("Rang taxon"),
            "url_obs": QCheckBox("URL observation"),
            "url_taxon": QCheckBox("URL taxon"),
            "observateur_id": QCheckBox("ID observateur"),
            "observateur_name": QCheckBox("Nom observateur"),
            "quality_grade": QCheckBox("Qualité"),
            "precision": QCheckBox("Precision")
        }
    
        for cb in champs_checks.values():
            cb.setChecked(True)
            champs_layout.addWidget(cb)
    
        champs_layout.addWidget(QLabel("Photos à exporter :"))
        radio_aucune = QRadioButton("Aucune photo")
        radio_une = QRadioButton("La première (ou seule) photo")
        radio_toutes = QRadioButton("Toutes les photos de l'observation")
        radio_toutes.setChecked(True)
    
        champs_layout.addWidget(radio_aucune)
        champs_layout.addWidget(radio_une)
        champs_layout.addWidget(radio_toutes)
    
        champs_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        champs_buttons.accepted.connect(champs_dialog.accept)
        champs_buttons.rejected.connect(champs_dialog.reject)
        champs_layout.addWidget(champs_buttons)
    
        champs_dialog.setLayout(champs_layout)
        champs_result = champs_dialog.exec_()
        if champs_result != QDialog.Accepted:
            print("❌ Annulé par utilisateur (champs/photos)")
            return
    
        champs_selectionnes = [k for k, cb in champs_checks.items() if cb.isChecked()]
    
        # Champs obligatoires (toujours présents)
        for forced in ["inat_id", "taxon_id"]:
            if forced not in champs_selectionnes:
                champs_selectionnes.append(forced)
    
        if radio_aucune.isChecked():
            photo_mode = "none"
        elif radio_une.isChecked():
            photo_mode = "one"
        else:
            photo_mode = "all"
    
        print(f"📋 Champs sélectionnés ({len(champs_selectionnes)}) : {champs_selectionnes}")
        print(f"📸 Mode photos choisi : {photo_mode}")
    
        # ---------- DÉFINITION DES CHAMPS ----------
        fields = QgsFields()
    
        champ_defs = {
            "inat_id": (QVariant.Int, None),
            "date_obs": (QVariant.DateTime, None),
            "scientific_name": (QVariant.String, 100),
            "vernacular_name_FR": (QVariant.String, 150),
            "latitude": (QVariant.Double, None),
            "longitude": (QVariant.Double, None),
            "place_guess": (QVariant.String, 200),
            "taxon_id": (QVariant.Int, None),
            "taxon_rank": (QVariant.String, 30),
            "url_obs": (QVariant.String, 200),
            "url_taxon": (QVariant.String, 150),
            "observateur_id": (QVariant.String, 50),
            "observateur_name": (QVariant.String, 100),
            "quality_grade": (QVariant.String, 20),
            "precision": (QVariant.Int, None)
        }
    
        # Champs obligatoires toujours présents
        if "inat_id" not in champs_selectionnes:
            champs_selectionnes.append("inat_id")
        if "taxon_id" not in champs_selectionnes:
            champs_selectionnes.append("taxon_id")
    
        # Ordre global de référence
        base_order = [
            "inat_id",
            "date_obs",
            "scientific_name",
            "vernacular_name_FR",
            "latitude",
            "longitude",
            "place_guess",
            "taxon_id",
            "taxon_rank",
            "url_obs",
            "url_taxon",
            "observateur_id",
            "observateur_name",
            "quality_grade",
            "precision",
        ]
    
        # Ordered_fields = intersection base_order ∩ champs_selectionnes
        ordered_fields = [c for c in base_order if c in champs_selectionnes]
    
        # Création des champs non-photo dans l'ordre défini
        for champ in ordered_fields:
            var_type, length = champ_defs[champ]
            if length:
                fields.append(QgsField(champ, var_type, len=length))
            else:
                fields.append(QgsField(champ, var_type))
    
        # Champs photo à la fin
        if photo_mode == "one":
            fields.append(QgsField("url_photo1", QVariant.String, len=250))
        elif photo_mode == "all":
            fields.append(QgsField("nb_photos", QVariant.Int))
            for i in range(1, max_photos + 1):
                fields.append(QgsField(f"url_photo{i}", QVariant.String, len=250))
    
        # Nom final de la couche iNat
        vl_name = f"iNat_{layer_name}_Ray={int(rayon_m)}m"
        vl = QgsVectorLayer("Point?crs=EPSG:4326", vl_name, "memory")
        pr = vl.dataProvider()
        pr.addAttributes(fields)
        vl.updateFields()
    
        # ---------- FEATURES ----------
        features = []
    
        for obs in all_obs:
            coords = obs.get('geojson', {}).get('coordinates')
            if not coords:
                continue
            lon, lat_obs = coords
    
            feat_out = QgsFeature(fields)
            feat_out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat_obs)))
    
            taxon = obs.get('taxon', {}) or {}
            user = obs.get('user', {}) or {}
            photos = obs.get('photos', []) or []
    
            date_py = obs.get('time_observed_at') or obs.get('observed_on')
            date_qt = QDateTime()
            if date_py:
                if isinstance(date_py, str):
                    date_qt = QDateTime.fromString(date_py, Qt.ISODate)
                else:
                    date_qt = QDateTime(
                        date_py.year, date_py.month, date_py.day,
                        date_py.hour, date_py.minute, date_py.second
                    )
            if not date_qt.isValid():
                date_qt = QDateTime.currentDateTime()
    
            sci = taxon.get('name')
            vern_fr = taxon.get('preferred_common_name')
            precision_val = obs.get('positional_accuracy')
            place_val = obs.get('place_guess')
    
            attrs = []
            for champ in ordered_fields:
                if champ == "inat_id":
                    attrs.append(obs.get('id'))
                elif champ == "date_obs":
                    attrs.append(date_qt)
                elif champ == "scientific_name":
                    attrs.append(sci)
                elif champ == "vernacular_name_FR":
                    attrs.append(vern_fr)
                elif champ == "latitude":
                    attrs.append(lat_obs)
                elif champ == "longitude":
                    attrs.append(lon)
                elif champ == "place_guess":
                    attrs.append(place_val)
                elif champ == "taxon_id":
                    attrs.append(taxon.get('id'))
                elif champ == "taxon_rank":
                    attrs.append(taxon.get('rank'))
                elif champ == "url_obs":
                    attrs.append(f"https://www.inaturalist.org/observations/{obs.get('id')}")
                elif champ == "url_taxon":
                    attrs.append(
                        f"https://www.inaturalist.org/taxa/{taxon.get('id')}"
                        if taxon.get('id') else None
                    )
                elif champ == "observateur_id":
                    attrs.append(user.get('login'))
                elif champ == "observateur_name":
                    attrs.append(user.get('name'))
                elif champ == "quality_grade":
                    attrs.append(obs.get('quality_grade'))
                elif champ == "precision":
                    attrs.append(precision_val)
    
            if photo_mode == "one":
                if photos:
                    p = photos[0]
                    if p and p.get('url'):
                        url = p['url']
                        url = url.replace('square.jpg', 'large.jpg') \
                                 .replace('square.jpeg', 'large.jpeg') \
                                 .replace('square.png', 'large.png')
                        attrs.append(url)
                    else:
                        attrs.append(None)
                else:
                    attrs.append(None)
    
            elif photo_mode == "all":
                nb = len(photos)
                photo_urls = []
                for p in photos:
                    if p and p.get('url'):
                        pu = p['url']
                        pu = pu.replace('square.jpg', 'large.jpg') \
                               .replace('square.jpeg', 'large.jpeg') \
                               .replace('square.png', 'large.png')
                        photo_urls.append(pu)
                    else:
                        photo_urls.append(None)
                photo_urls += [None] * (max_photos - len(photo_urls))
                attrs.append(nb)
                attrs.extend(photo_urls)
    
            feat_out.setAttributes(attrs)
            features.append(feat_out)
    
        pr.addFeatures(features)
        QgsProject.instance().addMapLayer(vl)
        iface.zoomToActiveLayer()
        print(f"✅ ETAPE 7 : {len(features)} obs (mode {photo_mode}, {len(champs_selectionnes)} champs non-photo)")
        iface.messageBar().pushSuccess("ETAPE 7", f"{len(features)} obs - {photo_mode}")
    
        # ---------- ETAPE 8 : enregistrement GPKG ----------
        project_path_out = QgsProject.instance().fileName()
        if project_path_out:
            proj_dir = os.path.dirname(project_path_out)
            layer_name_out = vl.name()
            safe_name = layer_name_out.replace(" ", "_")
            gpkg_path_out = os.path.join(proj_dir, f"{safe_name}.gpkg")
    
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = layer_name_out
            options.fileEncoding = "UTF-8"
    
            error, _ = QgsVectorFileWriter.writeAsVectorFormatV2(
                vl,
                gpkg_path_out,
                QgsProject.instance().transformContext(),
                options
            )
    
            if error == QgsVectorFileWriter.NoError:
                msg = f"GPKG enregistré : {gpkg_path_out}"
                print("💾", msg)
                iface.messageBar().pushSuccess("ETAPE 8", msg)
            else:
                print(f"❌ Erreur enregistrement GPKG (code {error})")
                iface.messageBar().pushWarning("ETAPE 8", f"Erreur GPKG (code {error})")
        else:
            print("ℹ️ Projet non enregistré : GPKG non créé (enregistrer le projet d'abord).")
            iface.messageBar().pushMessage(
                "ETAPE 8",
                "Projet non enregistré : impossible de créer le GPKG dans le dossier du projet.",
                level=Qgis.Warning
            )
    
        # ---------- ETAPE 8 bis : remplacer la couche mémoire par la couche GPKG ----------
        if project_path_out and 'error' in locals() and error == QgsVectorFileWriter.NoError:
            proj_local2 = QgsProject.instance()
    
            # Retirer la couche mémoire iNat
            if vl.id() in proj_local2.mapLayers():
                proj_local2.removeMapLayer(vl.id())
    
            # Recharger la couche iNat depuis le GPKG
            uri_inat = f"{gpkg_path_out}|layername={layer_name_out}"
            vl_perm = QgsVectorLayer(uri_inat, layer_name_out, "ogr")
    
            if vl_perm.isValid():
                proj_local2.addMapLayer(vl_perm)
                iface.setActiveLayer(vl_perm)
                print("✅ Couche iNat permanente chargée depuis le GPKG")
    
                # ---- Style simple : point jaune bordure rouge, 4 mm ----
                marker = QgsMarkerSymbol.createSimple({
                    "name": "circle",
                    "color": "255,255,0,255",          # jaune
                    "outline_color": "255,0,0,255",    # rouge
                    "outline_width": "0.4",
                    "outline_width_unit": "MM",
                    "size": "4",
                    "size_unit": "MM"
                })
                renderer = QgsSingleSymbolRenderer(marker)
                vl_perm.setRenderer(renderer)
                vl_perm.triggerRepaint()
                print("✅ Style iNat appliqué (point jaune, bordure rouge, 4 mm)")
            else:
                print("❌ Impossible de recharger la couche iNat depuis le GPKG")
    
        # ---------- Message final + retour SCR initial ----------
        msg = QMessageBox(iface.mainWindow())
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("iNaturalist Import – Finished / Terminé")
    
        msg.setText(
            "Processing finished.\n"
            f"You now have a new permanent layer \"{layer_name_out}\" with all iNaturalist "
            "information in its attribute table.\n\n"
            "Have fun!\n\n"
            "------------------------------------------------------------\n"
            "Traitement terminé.\n"
            f"Vous disposez maintenant d'une nouvelle couche permanente \"{layer_name_out}\" "
            "avec toutes les informations iNaturalist dans sa table d'attributs.\n\n"
            "Amusez-vous bien !"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
    
        proj.setCrs(initial_crs)
        canvas.setDestinationCrs(initial_crs)
        canvas.refresh()
        print(f"[DEBUG] Project CRS restored to initial: {initial_crs.authid()}")
        print(f"✅ SCR DU PROJET RESTAURÉ AU SCR INITIAL : {initial_crs.authid()}")
    
    # ==============================================================
    # 6) TOOL DE CERCLE EN 2154
    # ==============================================================
    
    class CircleByCenterRadiusTool(QgsMapTool):
        def __init__(self, canvas, target_layer, finish_callback):
            super().__init__(canvas)
            self.canvas = canvas
            self.layer = target_layer
            self.finish_callback = finish_callback
            self.rb = None
            self.center_map = None
            self.center_geo = None
            self.is_drawing = False
    
            self.da = QgsDistanceArea()
            self.da.setSourceCrs(
                self.canvas.mapSettings().destinationCrs(),
                QgsProject.instance().transformContext()
            )
            self.da.setEllipsoid(self.da.sourceCrs().ellipsoidAcronym())
    
            self.crs_proj = self.canvas.mapSettings().destinationCrs()  # EPSG:2154
            self.crs_geo = QgsCoordinateReferenceSystem("EPSG:4326")
            self.tr_to_geo = QgsCoordinateTransform(
                self.crs_proj, self.crs_geo, QgsProject.instance()
            )
    
        def activate(self):
            self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            color = self.canvas.selectionColor()
            color.setAlpha(80)
            self.rb.setColor(color)
            self.rb.setWidth(1)
            self.canvas.setCursor(Qt.CrossCursor)
    
        def deactivate(self):
            if self.rb:
                self.canvas.scene().removeItem(self.rb)
                self.rb = None
            self.canvas.unsetCursor()
            try:
                iface.statusBarIface().clearMessage()
            except:
                pass
    
        def canvasPressEvent(self, event):
            if event.button() != Qt.LeftButton:
                return
    
            map_point = self.toMapCoordinates(event.pos())
            if not self.is_drawing:
                self.center_map = map_point
                self.center_geo = self.tr_to_geo.transform(map_point)
                self.is_drawing = True
            else:
                radius_m = self.da.measureLine(self.center_map, map_point)
                radius_str, ok = QInputDialog.getText(
                    self.canvas,
                    "Circle radius / Rayon du cercle",
                    "Radius in meters:\nRayon en mètres :",
                    text=f"{radius_m:.1f}"
                )
                if not ok:
                    self._reset()
                    return
                try:
                    radius_m = float(radius_str.replace(",", "."))
                except ValueError:
                    self._reset()
                    return
    
                self._create_circle_feature(radius_m)
    
                lat = self.center_geo.y()
                lon = self.center_geo.x()
    
                msg = QMessageBox(iface.mainWindow())
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("iNaturalist Import - Geographic area (circle) / Zone géographique (cercle)")
                msg.setText(
                    "The extraction circle for iNaturalist has been created.\n\n"
                    f"Geometric data:\n"
                    f"- Center latitude: {lat:.6f}°\n"
                    f"- Center longitude: {lon:.6f}°\n"
                    f"- Radius: {radius_m:.1f} m\n\n"
                    "The project CRS will now be set to EPSG:4326 for the next steps.\n\n"
                    "------------------------------------------------------------\n"
                    "Cercle de définition de la zone d'extraction iNaturalist réalisé.\n\n"
                    f"Données géométriques :\n"
                    f"- Latitude centre : {lat:.6f}°\n"
                    f"- Longitude centre : {lon:.6f}°\n"
                    f"- Rayon : {radius_m:.1f} m\n\n"
                    "Le SCR du projet va maintenant être positionné sur EPSG:4326 pour la suite du traitement."
                )
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
    
                self._reset()
                self.canvas.unsetMapTool(self)
                self.finish_callback(lat, lon, radius_m)
    
        def canvasMoveEvent(self, event):
            if not self.is_drawing or self.center_map is None:
                return
            current_point = self.toMapCoordinates(event.pos())
            radius_m = self.da.measureLine(self.center_map, current_point)
            try:
                iface.statusBarIface().showMessage(f"Radius / Rayon : {radius_m:.1f} m")
            except:
                pass
            self._update_rubberband(radius_m)
    
        def _update_rubberband(self, radius_m, segments=72):
            if self.rb is None or self.center_map is None:
                return
            self.rb.reset(QgsWkbTypes.PolygonGeometry)
            center_geom = QgsGeometry.fromPointXY(self.center_map)
            circle_geom = center_geom.buffer(radius_m, segments)
            self.rb.setToGeometry(circle_geom, None)
    
        def _create_circle_feature(self, radius_m, segments=72):
            if self.layer is None or self.center_map is None:
                return
            center_geom = QgsGeometry.fromPointXY(self.center_map)
            circle_geom = center_geom.buffer(radius_m, segments)
            feat = QgsFeature(self.layer.fields())
            feat.setGeometry(circle_geom)
    
            lat = self.center_geo.y()
            lon = self.center_geo.x()
            field_names = self.layer.fields().names()
            if "lat" in field_names:
                feat["lat"] = lat
            if "lon" in field_names:
                feat["lon"] = lon
            if "rayon_m" in field_names:
                feat["rayon_m"] = radius_m
    
            self.layer.startEditing()
            self.layer.addFeature(feat)
            self.layer.commitChanges()
            self.layer.triggerRepaint()
    
        def _reset(self):
            self.is_drawing = False
            self.center_map = None
            self.center_geo = None
            if self.rb:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
            try:
                iface.statusBarIface().clearMessage()
            except:
                pass
    
    # ==============================================================
    # 7) FIN DU TOOL : SAUVEGARDE + STYLE + PASSAGE EN EPSG:4326
    # ==============================================================
    
    def finish_circle_tool(lat, lon, rayon):
        global circle_result
        global layer
        if "circle_result" not in globals():  #***
            circle_result = {}               #***    
            
        circle_result["lat"] = lat
        circle_result["lon"] = lon
        circle_result["rayon_m"] = rayon
    
        proj_local = QgsProject.instance()
        canvas_local = iface.mapCanvas()
    
        error = QgsVectorFileWriter.writeAsVectorFormat(
            layer, gpkg_path, "UTF-8", layer.crs(), "GPKG"
        )
    
        if error[0] == QgsVectorFileWriter.NoError:
            print(f"✅ GPKG créé : {gpkg_path}")
    
            if layer.id() in proj_local.mapLayers():
                proj_local.removeMapLayer(layer.id())
    
            uri_perm = f"{gpkg_path}|layername={layer_name}"
            layer_perm = QgsVectorLayer(uri_perm, layer_name, "ogr")
            if layer_perm.isValid():
                proj_local.addMapLayer(layer_perm)
                iface.setActiveLayer(layer_perm)
                print("✅ Couche permanente chargée")
    
                # STYLISATION DE LA COUCHE CERCLE_XX
                fill_symbol = QgsFillSymbol.createSimple({
                    "color": "255,0,255,85",
                    "outline_color": "255,0,0,255",
                    "outline_style": "solid",
                    "outline_width": "1",
                    "outline_width_unit": "MM",
                    "style": "solid",
                    "joinstyle": "bevel"
                })
                marker = QgsMarkerSymbol.createSimple({
                    "name": "circle",
                    "color": "magenta",
                    "outline_color": "red",
                    "outline_width": "0.2",
                    "outline_width_unit": "MM",
                    "size": "3",
                    "size_unit": "MM"
                })
                gg_opts = {
                    "geometryModifier": "centroid($geometry)",
                    "SymbolType": "Marker",
                    "units": "MapUnit"
                }
                gg_layer = QgsGeometryGeneratorSymbolLayer.create(gg_opts)
                gg_layer.setSubSymbol(marker)
                fill_symbol.appendSymbolLayer(gg_layer)
                renderer = QgsSingleSymbolRenderer(fill_symbol)
                layer_perm.setRenderer(renderer)
                layer_perm.triggerRepaint()
                print("✅ Style intégré appliqué (magenta circle + yellow/red center)")
            else:
                print("❌ Erreur chargement couche permanente")
        else:
            print(f"❌ Erreur sauvegarde : {error}")
    
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        proj_local.setCrs(wgs84_crs)
        canvas_local.setDestinationCrs(wgs84_crs)
        canvas_local.refresh()
        print(f"[DEBUG] Project CRS after switch to 4326: {proj_local.crs().authid()}")
        print("✅ PROJET EN EPSG:4326 POUR LA SUITE")
        print(f" lat={lat:.6f}, lon={lon:.6f}, rayon={rayon:.1f} m")
        print(f" GPKG : {gpkg_path}")
    
        # Enchaînement automatique vers ETAPE 7/8
        etape7_cercle_champs_et_photos()
    
    # ==============================================================
    # 8) LANCEMENT DU TOOL : BASCULE EN 2154 POUR LE DESSIN
    # ==============================================================
    
    print(f"[DEBUG] Project CRS before switch to 2154: {proj.crs().authid()}")
    lambert_crs = QgsCoordinateReferenceSystem("EPSG:2154")
    proj.setCrs(lambert_crs)
    canvas.setDestinationCrs(lambert_crs)
    canvas.refresh()
    print(f"[DEBUG] Project CRS after switch to 2154: {proj.crs().authid()}")
    
    temp_gpkg = os.path.join(project_path, f"{layer_name}_temp.gpkg")
    uri_tmp = f"{temp_gpkg}|layername={layer_name}"
    layer = QgsVectorLayer(uri_tmp, layer_name, "ogr")
    if not layer.isValid():
        layer = QgsVectorLayer(
            "Polygon?crs=epsg:2154"
            "&field=id:integer"
            "&field=lat:double(20,10)"
            "&field=lon:double(20,10)"
            "&field=rayon_m:double(20,3)",
            layer_name,
            "memory"
        )
    
    print(f"✅ Couche temporaire '{layer_name}' prête (sera sauvegardée en {os.path.basename(gpkg_path)})")
    if layer.id() not in [l.id() for l in proj.mapLayers().values()]:
        proj.addMapLayer(layer)
        iface.setActiveLayer(layer)
    
    tool = CircleByCenterRadiusTool(canvas, layer, finish_circle_tool)
    canvas.setMapTool(tool)
    print("✅ Tool actif : Clic1=centre, Clic2=rayon → cercle_XX.gpkg + EPSG:4326 + ETAPE 7/8")

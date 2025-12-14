# ==============================================================
# Plugin QGIS : iNaturalist Import
# Script     : yd_Script_2
# Version    : 1.0.0
# Rôle       : Ajout de la taxonomie (7 niveaux) aux données importées dans la couche ACTIVE
# Dépendance : pyinaturalist (pré-requis géré par Script 1)
# QGIS       : 3.40 (Bratislava)
# ==============================================================

from qgis.core import QgsVectorLayer, QgsField
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QProgressDialog, QMessageBox, QApplication
from qgis.utils import iface

from pyinaturalist.node_api import get_taxa

import csv
import os
import time
from datetime import datetime
from requests.exceptions import HTTPError

# PARAMÈTRES
taxon_field = "taxon_id"
TAX_FIELDS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# Throttling
SLEEP_BETWEEN_CALLS = 0.5
SLEEP_ON_429 = 60
MAX_RETRIES_429 = 3

def etape9_all_in_one_reload():

    # ==============================================================
    # === BEGIN CONTROLE COUCHE ACTIVE / TAXONOMIE (CAS 1 → 5) ===
    # ==============================================================

    active = iface.activeLayer()

    # --- CAS 1 : Aucune couche active ---
    if active is None:
        QMessageBox.warning(
            iface.mainWindow(),
            "CAS 1",
            "Aucune couche active"
        )
        return

    # --- CAS 2 : Couche active mais non conforme ---
    if not isinstance(active, QgsVectorLayer) or active.fields().indexOf("taxon_id") == -1:
        QMessageBox.warning(
            iface.mainWindow(),
            "iNaturalist Taxonomy - ATTENTION !",     
            "The active layer IS NOT an iNaturalist observation import vector layer.\n\n"
            "Please select a correct layer and restart the program.\n"
            "------------------------------------------------------------\n"
            "La couche active N'EST PAS une couche vectorielle d'importation d'observatios iNaturalist.\n\n"
            "Veuillez sélectionner une couche correcte et relancer le programme."
        )
        return

    fields = active.fields()
    kingdom_idx = fields.indexOf("kingdom")

    # --- CAS 3 & CAS 4 : champ kingdom existe ---
    if kingdom_idx != -1:

        from qgis.core import QgsFeatureRequest, QgsExpression

        expr = QgsExpression(
            '"kingdom" IS NULL OR trim("kingdom") = \'\''
        )
        req = QgsFeatureRequest(expr)
        req.setLimit(1)

        has_empty_kingdom = any(True for _ in active.getFeatures(req))

        # --- CAS 3 : champ kingdom existe MAIS au moins une valeur vide / NULL ---
        if has_empty_kingdom:
            QMessageBox.warning(
                iface.mainWindow(),
                "iNaturalist Taxonomy - ATTENTION !",     
                "The active layer appears to be corrupted and to have undergone"
                "an aborted process with this program.\n\n"
                "Please start from a clean situation by deleting this layer "
                "and running a new import (RECOMMENDED), "
                "or open the layer's attribute table in Edit mode, and manually delete "
                "all FIELDS between 'kingdom' (inclusive) and 'species' (inclusive).\n\n"
                "Then run this program again.\n\n"
                "------------------------------------------------------------\n"
                "La couche active semble corrompue et avoir fait l'objet "
                "d'un traitement avorté avec ce programme.\n\n"
                "Veuillez repartir d'une base saine en supprimant cette couche "
                "et en relancant une nouvelle importation (CONSEILLÉ), "
                "ou alors ouvrir la table d'attributs de la couche en mode Édition, et supprimer "
                "manuellement tous les CHAMPS entre 'kingdom' (compris) et 'species' (compris).\n\n"
                "Puis relancer ce programme."
            )
            return

        # --- CAS 4 : champ kingdom existe ET 100 % rempli ---
        QMessageBox.warning(
            iface.mainWindow(),
            "iNaturalist Taxonomy - ATTENTION !", 
            "The active layer has already been processed, and the taxonomy fields are already present and populated. "
            "Therefore, the program is complete.\n\n"
            "You can select another import layer of iNaturalist observations "
            "(not yet taxonomically processed) and restart this program.\n\n"
            "------------------------------------------------------------\n"
            "La couche active est déjà traitée et les champs de taxonomie sont déjà présents et remplis. "
            "Donc, fin du programme.\n\n"
            "Vous pouvez sélectionner une autre couche d'importation d'observations iNaturalist "
            "(non tratée en taxonomie) et relancer ce programme."
        )
        return

    # --- CAS 5 : champ kingdom absent, on continue ---
    # (aucune action, poursuite normale du script)

    # ==============================================================
    # === END CONTROLE COUCHE ACTIVE / TAXONOMIE (CAS 1 → 5) ===
    # ==============================================================
     
    start_time = datetime.now()
    
    src = active.source()
    parts = src.split("|layername=")
    if len(parts) != 2:
        QMessageBox.warning(
            iface.mainWindow(),
            "iNaturalist Import - ATTENTION !",
            "The active layer does not look like a GPKG source.\n\n"
            f"Source: {src}\n\n"
            "------------------------------------------------------------\n"
            "La couche active ne semble pas être une couche GPKG (source invalide).\n\n"
            f"Source : {src}"
        )
        return

    gpkg_path = parts[0]
    layer_name = parts[1]  # nom interne dans le GPKG

    base_dir = os.path.dirname(gpkg_path)
    taxa_csv_out = os.path.join(base_dir, "iNat_ETAPE9_taxa_ids.csv")
    taxo_csv_out = os.path.join(base_dir, "iNat_ETAPE9_taxonomie.csv")
    log_path = os.path.join(base_dir, "iNat_ETAPE9_all_in_one_RELOAD.log")

    # --- LOG ---
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(
            f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "=== ETAPE 9 (tout-en-un, reload) : début ===\n"
        )

    def log(msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(log_path, "a", encoding="utf-8") as lf2:
            lf2.write(line + "\n")

    # 1) Charger la couche GPKG (version fichier)
    if not os.path.exists(gpkg_path):
        log(f"❌ GPKG introuvable : {gpkg_path}")
        end_time = datetime.now()
        log(f"=== FIN avec erreur === Durée : {end_time - start_time}")
        return

    uri = f"{gpkg_path}|layername={layer_name}"
    vl = QgsVectorLayer(uri, layer_name, "ogr")

    if not vl.isValid():
        log("❌ Couche GPKG invalide")
        end_time = datetime.now()
        log(f"=== FIN avec erreur === Durée : {end_time - start_time}")
        return

    log(f"✅ Couche (fichier) chargée : {vl.name()} ({vl.featureCount()} entités)")

    taxon_idx = vl.fields().indexOf(taxon_field)
    if taxon_idx == -1:
        log(f"❌ Champ '{taxon_field}' introuvable")
        end_time = datetime.now()
        log(f"=== FIN avec erreur === Durée : {end_time - start_time}")
        return

    # 2) Extraire taxon_id uniques
    log("🔍 Extraction des taxon_id uniques...")

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
    log(f"✅ {len(taxa)} taxon_id uniques extraits")

    # 3) CSV taxon_id (optionnel)
    try:
        with open(taxa_csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["taxon_id", "scientific_name"])
            for tid in taxa:
                writer.writerow([tid, taxon_set[tid] or ""])
        log(f"💾 CSV taxon_id écrit : {taxa_csv_out}")
    except Exception as e:
        log(f"⚠️ Impossible d'écrire {taxa_csv_out} (continuation quand même) : {e}")

    # 4) Construction taxonomie (API + cache + throttling)
    log("🌳 Construction de la taxonomie via l'API iNaturalist (avec throttling)...")

    taxon_cache = {}  # id -> {"rank": r, "name": n, "ancestor_ids": [...]}

    def safe_get_taxa(tid):
        retries = 0
        while True:
            try:
                resp = get_taxa(taxon_id=tid)
                time.sleep(SLEEP_BETWEEN_CALLS)
                return resp
            except HTTPError as e:
                if "429" in str(e) and retries < MAX_RETRIES_429:
                    retries += 1
                    log(
                        f"⚠️ 429 pour taxon_id={tid}, tentative "
                        f"{retries}/{MAX_RETRIES_429}, pause {SLEEP_ON_429}s..."
                    )
                    time.sleep(SLEEP_ON_429)
                    continue
                else:
                    log(f"❌ HTTPError pour taxon_id={tid} : {e}")
                    return None
            except Exception as e:
                log(f"❌ Erreur pour taxon_id={tid} : {e}")
                return None

    def get_taxon_info(tid):
        if tid in taxon_cache:
            return taxon_cache[tid]
        resp = safe_get_taxa(tid)
        if not resp:
            taxon_cache[tid] = None
            return None
        results = resp.get("results", [])
        if not results:
            taxon_cache[tid] = None
            return None
        t = results[0]
        info = {
            "rank": t.get("rank"),
            "name": t.get("name"),
            "ancestor_ids": t.get("ancestor_ids") or [],
        }
        taxon_cache[tid] = info
        return info

    taxo_map = {}
    errors = 0

    # ---------- ProgressDialog TAXONS ----------
    nb_taxa = len(taxa)
    total_feats = vl.featureCount()

    progress_taxa = QProgressDialog(
        "",
        "Cancel / Annuler",
        0,
        nb_taxa,
        iface.mainWindow(),
    )
    progress_taxa.setWindowTitle(
        "STEP 9 – iNaturalist taxonomy / Taxonomie iNaturalist"
    )
    progress_taxa.setWindowModality(Qt.WindowModal)
    progress_taxa.setMinimumDuration(0)
    progress_taxa.resize(progress_taxa.width() * 3, progress_taxa.height())

    def update_taxa_label(current, total, tid):
        progress_taxa.setLabelText(
            "Taxonomy processing in progress...\n"
            f"- Total records: {total_feats}\n"
            f"- Unique taxa: {nb_taxa}\n"
            f"- Currently processing taxon {current}/{total} (id={tid})\n\n"
            "------------------------------------------------------------\n"
            "Traitement taxonomique en cours...\n"
            f"- Nombre total d'enregistrements : {total_feats}\n"
            f"- Nombre de taxons répertoriés : {nb_taxa}\n"
            f"- Traitement du taxon {current}/{total} (id={tid})"
        )

    processed = 0
    for tid in taxa:
        processed += 1

        if progress_taxa.wasCanceled():
            log("⚠️ Traitement taxonomique annulé par l'utilisateur.")
            break

        progress_taxa.setValue(processed)
        update_taxa_label(processed, nb_taxa, tid)
        QApplication.processEvents()

        info = get_taxon_info(tid)
        if not info:
            log(f"⚠️ Aucun résultat pour taxon_id={tid}")
            errors += 1
            taxo_map[tid] = {field: "" for field in TAX_FIELDS}
            continue

        self_rank = info["rank"]
        self_name = info["name"]
        ancestor_ids = info["ancestor_ids"]

        rank_to_name = {}
        for aid in ancestor_ids:
            ainfo = get_taxon_info(aid)
            if not ainfo:
                continue
            r = ainfo.get("rank")
            n = ainfo.get("name")
            if r and n and r in TAX_FIELDS and r not in rank_to_name:
                rank_to_name[r] = n

        if self_rank in TAX_FIELDS and self_name:
            rank_to_name[self_rank] = self_name

        taxo_map[tid] = {field: rank_to_name.get(field, "") for field in TAX_FIELDS}

    progress_taxa.close()
    log(f"✅ Taxonomie construite pour {len(taxo_map)} taxon_id, erreurs API : {errors}")

    # 5) CSV taxonomique (optionnel)
    try:
        with open(taxo_csv_out, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.writer(out_f, delimiter=";")
            header = ["taxon_id"] + TAX_FIELDS
            writer.writerow(header)
            for tid in taxa:
                row = [tid] + [taxo_map[tid].get(field, "") for field in TAX_FIELDS]
                writer.writerow(row)
        log(f"💾 CSV taxonomique écrit : {taxo_csv_out}")
    except Exception as e:
        log(f"⚠️ Impossible d'écrire {taxo_csv_out} (continuation quand même) : {e}")

    # 6) Intégration dans le GPKG (couche fichier vl)
    log("🧬 Intégration directe de la taxonomie dans la couche (fichier)...")

    provider = vl.dataProvider()
    existing_fields = [f.name() for f in vl.fields()]
    new_fields = []

    for field_name in TAX_FIELDS:
        if field_name not in existing_fields:
            new_fields.append(QgsField(field_name, QVariant.String, len=150))

    if new_fields:
        log(
            "➕ Ajout de "
            f"{len(new_fields)} champs taxonomiques : "
            f"{', '.join(f.name() for f in new_fields)}"
        )
        provider.addAttributes(new_fields)
        vl.updateFields()
    else:
        log("ℹ️ Tous les champs taxonomiques existent déjà")

    idx_map = {name: vl.fields().indexOf(name) for name in TAX_FIELDS}

    if not vl.isEditable():
        vl.startEditing()

    n_updated = 0
    n_not_found = 0

    log("✏️ Mise à jour des entités dans le fichier...")

    # ---------- ProgressDialog ENTITÉS ----------
    total_feats = vl.featureCount()
    progress_feats = QProgressDialog(
        "Updating taxonomy in the layer...\n"
        f"{total_feats} features to update.",
        "Cancel / Annuler",
        0,
        total_feats,
        iface.mainWindow(),
    )
    progress_feats.setWindowTitle("STEP 9 – Layer update / Mise à jour de la couche")
    progress_feats.setWindowModality(Qt.WindowModal)
    progress_feats.setMinimumDuration(0)

    i_feat = 0
    for feat in vl.getFeatures():
        i_feat += 1

        if progress_feats.wasCanceled():
            log("⚠️ Mise à jour des entités annulée par l'utilisateur.")
            break

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

        for field_name in TAX_FIELDS:
            idx = idx_map[field_name]
            feat[idx] = taxo.get(field_name, "")

        if not vl.updateFeature(feat):
            log(f"⚠️ Échec updateFeature pour FID={feat.id()}")
        else:
            n_updated += 1

    progress_feats.close()

    if vl.commitChanges():
        log(
            "✅ Intégration terminée dans le fichier : "
            f"{n_updated} entités MAJ, {n_not_found} sans taxonomie"
        )
    else:
        log("❌ Erreur lors du commit sur fichier, annulation")
        vl.rollBack()

    # 7) Reload de la couche active si elle pointe sur ce GPKG
    log("🔄 Tentative de reload de la couche active...")

    active2 = iface.activeLayer()
    if active2 and isinstance(active2, QgsVectorLayer):
        src2 = active2.source().replace("\\", "/")
        gpkg_norm = gpkg_path.replace("\\", "/")
        if gpkg_norm in src2:
            active2.reload()
            active2.triggerRepaint()
            log("✅ Couche active rechargée (style conservé)")
        else:
            log(
                "ℹ️ Couche active ne pointe pas sur ce GPKG "
                f"({gpkg_norm} not in {src2}), aucun reload effectué."
            )
    else:
        log("ℹ️ Pas de couche active ou couche non vectorielle, aucun reload effectué.")

    end_time = datetime.now()
    log(f"Durée totale Taxonomy : {end_time - start_time}")
    log("=== FIN Taxonomy ===")

    # --- Timing information ---
    start_str = start_time.strftime("%H:%M:%S")
    end_str = end_time.strftime("%H:%M:%S")

    duration_td = end_time - start_time
    total_seconds = int(duration_td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    duration_str = f"{h:02d}:{m:02d}:{s:02d}"

    # ---------- Boîte finale FR/EN ----------
    msg = QMessageBox(iface.mainWindow())
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("iNaturalist Taxonomy – Finished / Terminé")
    msg.setText(
        f"Start time / Heure de début : {start_str}\n"
        f"End time / Heure de fin : {end_str}\n"
        f"Processing time / Temps de traitement : {duration_str}\n\n"       
        "------------------------------------------------------------\n\n" 
        "PROCESSING FINISHED\n\n"        
        f"The allocation table for your layer \"{layer_name}\" now contains the full "
        "taxonomy for all observed specimens.\n\n"
        "Have fun!\n\n"
        "------------------------------------------------------------\n\n"
        "TRAITEMENT TERMINÉ\n\n"   
        f"La table d'allocation de votre couche \"{layer_name}\" contient maintenant "
        "la taxonomie complète des spécimens observés.\n\n"
        "Amusez-vous bien !"
    )
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()


# Lancer
#*** Execution moved to plugin entry point


def yd_run(iface):  #*** Plugin entry point
    etape9_all_in_one_reload()
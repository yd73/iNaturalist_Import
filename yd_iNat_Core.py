# -*- coding: utf-8 -*-
# ==============================================================
# iNaturalist - Core Query Engine
# --------------------------------------------------------------
# Fichier   : yd_iNat_Core.py
# Role      : Coeur des requetes iNaturalist avec pagination
# Auteur    : Yves Durivault / ChatGPT
# API       : https://api.inaturalist.org/v1/observations
# ==============================================================

import time
import requests
from requests.exceptions import RequestException

INAT_API_URL = "https://api.inaturalist.org/v1/observations"
INAT_TAXA_URL = "https://api.inaturalist.org/v1/taxa"


def resolve_taxon_id(taxon_name):
    """
    Résout un nom de taxon (famille, genre, espèce) en taxon_id.
    
    Exemple :
        resolve_taxon_id("Lepidoptera") → 47157
        resolve_taxon_id("Panthera leo") → 41970
    
    Retourne None si le taxon n'est pas trouvé.
    """
    if not taxon_name:
        return None
    
    params = {
        "q": taxon_name,
        "per_page": 1
    }
    
    try:
        response = requests.get(INAT_TAXA_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            return None
        
        taxon_id = results[0].get("id")
        return taxon_id
        
    except RequestException as e:
        print(f"⚠️  Erreur résolution taxon '{taxon_name}': {e}")
        return None


def count_inat_observations(
    *,
    lat,
    lng,
    radius_km,
    d1=None,
    d2=None,
    month=None,
    user_login=None,
    taxon_name=None,
    quality_grade=None,
    locale="en"
):
    """
    Compte le nombre total d'observations correspondant aux critères
    SANS les télécharger (requête rapide avec per_page=1).
    
    Returns:
        int: Nombre total d'observations, ou None si erreur
    """
    params = {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "per_page": 1,  # Une seule observation suffit pour avoir total_results
        "page": 1,
        "locale": locale,
    }
    
    # Filtrage par dates
    if month:
        # month peut être un entier ou une liste d'entiers
        if isinstance(month, list):
            params["month"] = ",".join(str(m) for m in month)
        else:
            params["month"] = month
    else:
        if d1 and d1 not in ("Toutes", "All / Tous", ""):
            params["d1"] = d1
        if d2 and d2 not in ("Toutes", "All / Tous", ""):
            params["d2"] = d2
    
    # Filtres optionnels
    if user_login:
        params["user_login"] = user_login
    
    if taxon_name:
        taxon_id = resolve_taxon_id(taxon_name)
        if taxon_id:
            params["taxon_id"] = taxon_id
    
    if quality_grade:
        params["quality_grade"] = quality_grade
    
    if locale == "fr":
        params["preferred_place_id"] = 6753
    
    try:
        response = requests.get(INAT_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("total_results", 0)
    except RequestException as e:
        print(f"⚠️  Erreur comptage observations: {e}")
        return None


def run_inat_query(
    *,
    lat,
    lng,
    radius_km,
    per_page=200,
    max_pages=50,
    max_results=10000,
    delay_sec=1.0,
    diagnostic=False,
    locale="en",
    d1=None,
    d2=None,
    month=None,
    user_login=None,
    taxon_name=None,
    quality_grade=None,
    progress_callback=None,
):
    """
    Execute une requête iNaturalist paginée et sécurisée.
    
    IMPORTANT: En cas de dépassement de max_results, s'arrête à la dernière
    DATE COMPLÈTE pour éviter les imports partiels d'une journée.
    
    Paramètres :
        lat, lng : Coordonnées du centre de recherche
        radius_km : Rayon de recherche en km
        d1, d2 : Dates de début et fin (format "YYYY-MM-DD")
        month : Mois spécifique (1-12) - filtre sur toutes les années
        user_login : Filtrer par utilisateur iNaturalist
        taxon_name : Nom du taxon (résolu en taxon_id)
        quality_grade : Qualité des observations (research, casual, needs_id)
        locale : Langue ("en" ou "fr")
        progress_callback : Fonction appelée avec (current, total, message) pour progression
        
    Note : Si month est fourni, d1 et d2 sont ignorés.
    
    Returns:
        dict: {
            'observations': list,  # Liste des observations
            'metadata': {
                'total_requested': int,     # Nombre total disponible
                'total_imported': int,      # Nombre réellement importé
                'limit_reached': bool,      # True si limite atteinte
                'last_complete_date': str,  # Dernière date complète (YYYY-MM-DD)
                'excluded_count': int       # Nombre d'observations exclues
            }
        }
    """
    
    results = []
    page = 1
    total_available = None
    date_counts = {}  # Compteur par date d'observation
    limit_reached = False

    while page <= max_pages and len(results) < max_results:

        params = {
            "lat": lat,
            "lng": lng,
            "radius": radius_km,
            "per_page": per_page,
            "page": page,
            "order": "desc",
            "order_by": "observed_on",  # IMPORTANT: Tri par date d'observation (pas created_at)
            "locale": locale,
        }
        
        # FILTRAGE PAR DATES
        if month:
            # month peut être un entier ou une liste d'entiers
            if isinstance(month, list):
                # Liste de mois → "1,2,3"
                params["month"] = ",".join(str(m) for m in month)
                if diagnostic:
                    print(f"  → Filtre mois : {params['month']} (toutes années)")
            else:
                # Un seul mois
                params["month"] = month
                if diagnostic:
                    print(f"  → Filtre mois : {month} (toutes années)")
        else:
            if d1 and d1 not in ("Toutes", "All / Tous", ""):
                params["d1"] = d1
            if d2 and d2 not in ("Toutes", "All / Tous", ""):
                params["d2"] = d2
        
        # Ajout des filtres optionnels
        if user_login:
            params["user_login"] = user_login
        
        # Résoudre taxon_name en taxon_id
        if taxon_name:
            taxon_id = resolve_taxon_id(taxon_name)
            if taxon_id:
                params["taxon_id"] = taxon_id
                if diagnostic:
                    print(f"  → Taxon '{taxon_name}' résolu en taxon_id={taxon_id}")
            else:
                if diagnostic:
                    print(f"  ⚠️  Taxon '{taxon_name}' non trouvé, ignoré")
        
        if quality_grade:
            params["quality_grade"] = quality_grade
        
        if locale == "fr":
            params["preferred_place_id"] = 6753

        if diagnostic:
            print("\n=== REQUETE iNaturalist ===")
            print(f"URL : {INAT_API_URL}")
            print("Parametres :")
            for k, v in params.items():
                print(f"  {k} = {v}")

        try:
            response = requests.get(
                INAT_API_URL,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        except RequestException as e:
            raise RuntimeError(f"Erreur iNaturalist : {e}")

        # Sauvegarder le total disponible (première page)
        if total_available is None:
            total_available = data.get("total_results", 0)
            # Notifier le total disponible
            if progress_callback:
                progress_callback(0, min(total_available, max_results), "Starting download...")
        
        page_results = data.get("results", [])

        if diagnostic:
            print("\n=== REPONSE iNaturalist ===")
            print(f"total_results = {total_available}")
            print(f"Resultats recus : {len(page_results)}")

        if not page_results:
            break

        # Ajouter les observations et compter par date
        for obs in page_results:
            obs_date = obs.get("observed_on", "unknown")
            date_counts[obs_date] = date_counts.get(obs_date, 0) + 1
            results.append(obs)
            
            # Notifier progression
            if progress_callback and len(results) % 50 == 0:  # Mise à jour tous les 50
                progress_callback(
                    len(results), 
                    min(total_available, max_results),
                    f"Downloading observations..."
                )

            if len(results) >= max_results:
                limit_reached = True
                if diagnostic:
                    print(f"\n⚠️  Plafond max_results ({max_results}) atteint")
                break
        
        # Mise à jour après chaque page
        if progress_callback:
            progress_callback(
                len(results),
                min(total_available, max_results),
                f"Downloaded {len(results)} observations..."
            )
        
        if limit_reached:
            break

        page += 1
        time.sleep(delay_sec)
    
    # =====================================================================
    # POST-TRAITEMENT : Supprimer la dernière date si limite atteinte
    # =====================================================================
    last_complete_date = None
    excluded_count = 0
    
    if limit_reached and results:
        # Trouver la dernière date (la plus ancienne car ordre DESC)
        last_date = results[-1].get("observed_on", None)
        
        if last_date and last_date != "unknown":
            # Supprimer TOUTES les observations de cette date (potentiellement incomplète)
            results_clean = [obs for obs in results if obs.get("observed_on") != last_date]
            excluded_count = len(results) - len(results_clean)
            
            if diagnostic:
                print(f"\n📅 Arrêt propre à la dernière date complète:")
                print(f"   - Date incomplète exclue: {last_date}")
                print(f"   - Observations exclues: {excluded_count}")
                print(f"   - Import final: {len(results_clean)} observations")
            
            # Trouver la dernière date complète (première date après nettoyage)
            if results_clean:
                last_complete_date = results_clean[-1].get("observed_on")
            
            results = results_clean
    
    # Construire les métadonnées
    metadata = {
        'total_requested': total_available or 0,
        'total_imported': len(results),
        'limit_reached': limit_reached,
        'last_complete_date': last_complete_date,
        'excluded_count': excluded_count
    }
    
    return {
        'observations': results,
        'metadata': metadata
    }
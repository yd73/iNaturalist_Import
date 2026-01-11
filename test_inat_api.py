#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour explorer la structure des données iNaturalist API v1
"""

import sys
import json
import requests
from pprint import pprint

# Simulation de yd_iNat_Core (version simplifiée pour test)
def test_inat_query(lat, lng, radius_km, per_page=5):
    """Requête de test à l'API iNaturalist"""
    
    url = "https://api.inaturalist.org/v1/observations"
    
    params = {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "per_page": per_page,
        "page": 1,
        "order": "desc",
        "order_by": "created_at",
        "locale": "fr",
        "preferred_place_id": 6753  # France
    }
    
    print("=== REQUÊTE API ===")
    print(f"URL: {url}")
    print(f"Paramètres: {json.dumps(params, indent=2)}")
    print()
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print("=== RÉPONSE API ===")
        print(f"Total résultats: {data.get('total_results', 0)}")
        print(f"Page: {data.get('page', 0)}")
        print(f"Par page: {data.get('per_page', 0)}")
        print(f"Résultats reçus: {len(data.get('results', []))}")
        print()
        
        return data
        
    except Exception as e:
        print(f"ERREUR: {e}")
        return None


def extract_observation_fields(obs):
    """Extrait et affiche les champs d'une observation"""
    
    print("\n" + "="*80)
    print(f"OBSERVATION ID: {obs.get('id')}")
    print("="*80)
    
    # Extraction selon le mapping défini
    fields = {}
    
    # inat_id (obligatoire)
    fields['inat_id'] = obs.get('id')
    
    # date_obs
    fields['date_obs'] = obs.get('observed_on')
    
    # Taxon
    taxon = obs.get('taxon')
    if taxon:
        fields['taxon_id'] = taxon.get('id')
        fields['scientific_name'] = taxon.get('name')
        fields['vernacular_name_FR'] = taxon.get('preferred_common_name')
        fields['taxon_rank'] = taxon.get('rank')
        fields['url_taxon'] = f"https://www.inaturalist.org/taxa/{taxon.get('id')}"
    else:
        fields['taxon_id'] = None
        fields['scientific_name'] = None
        fields['vernacular_name_FR'] = None
        fields['taxon_rank'] = None
        fields['url_taxon'] = None
    
    # Coordonnées
    location = obs.get('location')
    if location:
        coords = location.split(',')
        fields['latitude'] = float(coords[0])
        fields['longitude'] = float(coords[1])
    else:
        fields['latitude'] = None
        fields['longitude'] = None
    
    # Place
    fields['place_guess'] = obs.get('place_guess')
    
    # URL observation
    fields['url_obs'] = obs.get('uri')
    
    # Utilisateur
    user = obs.get('user')
    if user:
        fields['observateur_id'] = user.get('id')
        fields['observateur_name'] = user.get('login')
    else:
        fields['observateur_id'] = None
        fields['observateur_name'] = None
    
    # Qualité et précision
    fields['quality_grade'] = obs.get('quality_grade')
    fields['precision'] = obs.get('positional_accuracy')
    
    # Photos
    observation_photos = obs.get('observation_photos', [])
    fields['nbr_photos'] = len(observation_photos)
    
    # Affichage
    print("\n--- CHAMPS PRINCIPAUX ---")
    for key, value in fields.items():
        if key != 'nbr_photos':  # On affiche les photos séparément
            print(f"{key:25} : {value}")
    
    # Détail des photos
    if observation_photos:
        print(f"\n--- PHOTOS ({len(observation_photos)}) ---")
        for idx, obs_photo in enumerate(observation_photos, start=1):
            photo = obs_photo.get('photo', {})
            photo_id = photo.get('id')
            photo_url = photo.get('url')
            
            print(f"\nPhoto {idx}:")
            print(f"  photo_rank     : {idx}")
            print(f"  photo_label    : Photo{idx}")
            print(f"  photo_id       : {photo_id}")
            print(f"  identifier (URL): {photo_url}")
    else:
        print("\n--- PHOTOS ---")
        print("Aucune photo")
    
    return fields


def main():
    """Test principal"""
    
    print("="*80)
    print("TEST API iNaturalist - Exploration structure de données")
    print("="*80)
    print()
    
    # Coordonnées de test (Paris)
    lat = 48.8566
    lng = 2.3522
    radius = 5  # km
    
    print(f"Zone de test: Paris ({lat}, {lng}), rayon {radius} km")
    print()
    
    # Requête
    data = test_inat_query(lat, lng, radius)
    
    if not data:
        print("Pas de données reçues")
        return
    
    results = data.get('results', [])
    
    if not results:
        print("Aucune observation trouvée")
        return
    
    print(f"\n{'='*80}")
    print(f"ANALYSE DE {len(results)} OBSERVATIONS")
    print(f"{'='*80}")
    
    # Analyser chaque observation
    for obs in results:
        extract_observation_fields(obs)
    
    # Statistiques globales
    print("\n" + "="*80)
    print("STATISTIQUES GLOBALES")
    print("="*80)
    
    with_taxon = sum(1 for obs in results if obs.get('taxon'))
    with_photos = sum(1 for obs in results if obs.get('observation_photos'))
    with_coords = sum(1 for obs in results if obs.get('location'))
    with_vernacular = sum(1 for obs in results if obs.get('taxon', {}).get('preferred_common_name'))
    
    print(f"Observations avec taxon      : {with_taxon}/{len(results)}")
    print(f"Observations avec photos     : {with_photos}/{len(results)}")
    print(f"Observations avec coordonnées: {with_coords}/{len(results)}")
    print(f"Observations avec nom FR     : {with_vernacular}/{len(results)}")
    
    # Afficher une observation complète en JSON pour référence
    if results:
        print("\n" + "="*80)
        print("EXEMPLE: Structure JSON complète de la première observation")
        print("="*80)
        print(json.dumps(results[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
# iNaturalist Import

Plugin QGIS permettant :
- l’extraction de données iNaturalist à partir d’une zone circulaire, et avec filtrage des données d'entrée ET de sortie.
- facultativement et indépendamment, l’enrichissement taxonomique des observations (7 niveaux).

## Version
1.0.0

## Compatibilité
- QGIS 3.28+
- Testé sous QGIS 3.40 (Bratislava)

## Fonctionnalités
   * Premier module :
	- Sélection interactive d’une zone circulaire
	- Filtrage d'entrée (période, observateur, taxon, ...)
	- Filtrage de sortie (quelschampsb on veut récupérer)
	- Import des observations iNaturalist
	- Sauvegarde au format GeoPackage.
	
   * Second module :	
	- Sur choix de la couche (couche ACTIVE, ajout automatique de la taxonomie à 7 niveaux :
		  - kingdom
		  - phylum
		  - class
		  - order
		  - family
		  - genus
		  - species

## Dépendances
- Ce plugin nécessite la bibliothèque Python **pyinaturalist**. 
  Si elle n’est pas installée, le plugin affiche une boîte de dialogue
  expliquant la procédure précise d’installation..
## Utilisation
1. Cliquer sur le bouton d’import iNaturalist,
2. Définir la zone circulaire sur la carte (centre et rayon, ce dernier graphiquement ou numériquement),
3. Choisir les données de filtrage d'entrée,
4. Choisir les données de filtrage de sortie,
5. Laisser le script s’exécuter jusqu’à la création de la couche
6. (Optionnel) Après avoir rendue ACTIVE la couche nouvellement créée, Lancer l’outil d’enrichissement taxonomique.

## Notes
- Ce plugin est indépendant du plugin « iNaturalist Extract » existant
- Tous les noms internes sont préfixés par `yd_`

## Auteur
Yves DURIVAULT

## Licence
GPL v3


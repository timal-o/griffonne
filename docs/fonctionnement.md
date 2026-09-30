# Fonctionnement de Griffonne

Ce document décrit la chaîne de traitement, de la feuille imprimée au fichier de police.

```
 layout.py            scan.py                     build.py
┌──────────┐    ┌────────────────────┐    ┌──────────────────────────┐
│ feuille  │ →  │ 4 coins → homographie │ →  │ potrace → variantes →    │ → .otf / .ttf
│ PDF A4   │    │ orientation, page n°  │    │ règles calt (GSUB)       │
└──────────┘    │ crop des cases        │    └──────────────────────────┘
   imprimer     └────────────────────┘
      ↓ écriture ↓ scan/photo
```

## 1. La feuille modèle (`layout.py`)

Toute la géométrie est en **millimètres**, dans un seul module utilisé à la fois pour dessiner la feuille et pour relire le scan. Les deux ne peuvent donc pas se désynchroniser.

| Élément | Valeur |
|---|---|
| Page | A4, 210 × 297 mm |
| Grille | 10 colonnes × 10 lignes = 100 cases par page |
| Case | 18 × 24 mm : 4 mm d'étiquette + 20 mm de zone d'écriture |
| Lignes-guides | ascendante à 2,5 mm, hauteur d'x à 8 mm (pointillés), **ligne de base à 14,5 mm** (pleine) |
| Couleur des guides | bleu clair, qui disparaît au seuillage |

Chaque page porte :

- **4 carrés noirs de 8 mm** aux coins : points de référence pour le redressement ;
- une **marque d'orientation** (petit carré près du coin haut-gauche) ;
- un **numéro de page en binaire** (7 petits carrés : un bit de départ toujours plein, puis 6 bits).

Le modèle (jeux de caractères + nombre de variantes) est enregistré dans `work/spec.json`. Changer le modèle efface les scans, car les cases ne correspondraient plus.

## 2. Lecture du scan (`scan.py`)

1. **Détection des coins** : normalisation de l'éclairage (division par un fond estimé par fermeture morphologique), seuillage, puis recherche des 4 plus grandes formes pleines et carrées.
2. **Orientation** : les 4 rotations possibles (0/90/180/270°) sont essayées. On garde celle où la marque d'orientation et le bit de départ sont noirs.
3. **Numéro de page** : lu sur les carrés binaires. Les pages peuvent donc être envoyées dans n'importe quel ordre.
4. **Redressement** : homographie vers une image de référence à **12 pixels par mm**, puis nouvelle normalisation de l'éclairage.
5. **Extraction** : chaque case est découpée avec une marge de 0,7 mm (pour éviter les bords imprimés), seuillée, et débarrassée des poussières.

Le redressement s'appuie sur les positions des coins, pas sur la taille de l'image : l'impression à une échelle légèrement différente de 100 % ne casse rien.

## 3. Vectorisation (`build.py`)

Pour chaque glyphe :

1. rognage autour de l'encre, sur-échantillonnage ×2 et léger flou pour adoucir les contours ;
2. seuillage puis tracé avec **Potrace**, qui produit des courbes de Bézier cubiques ;
3. conversion en unités de police : 1 mm de papier = 62,5 unités (UPM = 1000), origine sur la **ligne de base** ;
4. décalage horizontal pour que le bord gauche de l'encre tombe sur la marge choisie, avance = largeur + 2 marges ;
5. orientation des contours (anti-horaire pour CFF, horaire pour TrueType).

Le `.otf` utilise les courbes cubiques directement. Le `.ttf` les convertit en quadratiques (`cu2qu`).

## 4. Variantes

### Variantes réelles et synthétiques

Chaque caractère reçoit exactement **N variantes** (réglage « Variantes par caractère »). Les versions réellement écrites viennent en premier. S'il en manque, des variantes synthétiques sont dérivées d'une version réelle tirée au hasard, avec :

- rotation, échelle horizontale et verticale, cisaillement ;
- décalage vertical ;
- ondulation douce (déformation sinusoïdale de tous les points, y compris de contrôle).

La force est réglée par le curseur « Variations synthétiques ». Avoir le **même nombre de variantes pour tous les caractères** simplifie les règles ci-dessous.

### Nommage

Pour un caractère `a` (U+0061) : `uni0061` (forme de base, mappée dans le `cmap`), puis `uni0061.v1`, `uni0061.v2`… (non mappées, accessibles seulement par substitution).

### Règle `calt`

Le moteur de texte remplace la forme de base par une variante, en regardant les glyphes voisins. Il n'y a **pas de vrai tirage aléatoire** : le choix est une fonction du contexte, avec une table pseudo-aléatoire fixée au moment de la génération (graine `seed`).

Soit `@Vj` la classe de toutes les variantes d'indice `j`. Les règles sont écrites dans cet ordre, la première qui correspond gagne :

```fea
# 1. deux glyphes de contexte : la variante suivante dépend des deux précédentes
sub @V2 @V0 @base' by @V3;      # N² règles, cible tirée au hasard, toujours ≠ précédente

# 2. un seul glyphe de contexte (2e lettre d'un mot)
sub @V1 @base' by @V4;

# 3. début de mot : variante choisie d'après la lettre suivante
sub @base' [b c d …] by @V2;
```

Propriétés :

- une même lettre n'apparaît jamais deux fois de suite sous la même forme (`eeee` alterne) ;
- comme la cible dépend des **deux** variantes précédentes, les séquences ne se répètent pas en boucle courte ;
- le même texte donne toujours le même rendu, ce qui évite le scintillement à l'édition.

Le bouton **« Autre tirage »** change la graine et régénère la police.

> Une règle `rand` a été essayée puis retirée : les navigateurs l'activent d'office et re-tirent au hasard à chaque affichage, ce qui fait bouger le texte pendant la frappe et empêche de désactiver les variantes.

## 5. Assemblage

`fontTools.fontBuilder.FontBuilder` construit les tables (`cmap`, `hmtx`, `hhea`, `OS/2`, `name`, `post`, plus `CFF ` ou `glyf`). Les règles `calt` sont écrites en langage de feature (`.fea`) puis compilées avec `feaLib`.

| Métrique | Valeur |
|---|---|
| Unités par em | 1000 |
| Ascendante / descendante | 850 / −350 |
| Hauteur de capitale | 750 |
| Glyphe `.notdef` | rectangle creux |

## 6. Interface et API

`app.py` est un serveur HTTP local (bibliothèque standard, une seule adresse : `127.0.0.1`).

| Route | Rôle |
|---|---|
| `GET /api/charsets` | jeux de caractères disponibles |
| `POST /api/spec` | définit le modèle (`groups`, `variants`) |
| `GET /api/template.pdf` | feuille à imprimer |
| `GET /api/template.png?page=n` | aperçu d'une page |
| `POST /api/upload` | corps = image brute ; renvoie `{page, total}` |
| `GET /api/state?t=150` | état des cases pour un seuil donné |
| `GET /api/cell?i=&t=` | miniature d'une case |
| `POST /api/reset` | efface les scans |
| `POST /api/build` | construit la police (voir `Settings` dans `build.py`) |
| `GET /out/<fichier>` | police générée (`?dl=1` pour télécharger) |

## 7. Pistes d'amélioration

- ligatures et lettres liées ;
- crénage automatique ;
- réglage d'espacement par glyphe ;
- tirage réellement aléatoire pour les applications qui le supportent ;
- import d'une feuille personnalisée (autres langues, symboles) ;
- export WOFF2.

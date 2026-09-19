# These : caracteriser les fenetres non datees et les pertes

Decision documentaire du 15 septembre 2026. Travail methodologique a realiser
separement ; aucune analyse ni conclusion scientifique produite dans ce lot.

## Objectif

L'archive preserve les features mais ne corrige pas automatiquement le biais
des resumes dates, dont elle reste exclue. Etudier volontairement cette archive,
les compteurs du firmware et les conditions de collecte pour decrire les pertes
et leurs associations possibles avec le contexte du domain shift.

## Mesures a definir avant collecte

- Proportion non datee parmi les fenetres recues : N archives uniques / (N archives
  uniques + N fenetres datees comparables). Separer devices, profils et sessions ;
  ne pas compter les retransmissions comme de nouvelles observations.
- Proportion conservee parmi les acquisitions tentees : rapprocher les compteurs
  windows_attempted, imu_invalid, dated_created, untimed_created et les pertes.
  Les nombres serveur seuls ne donnent pas les fenetres jamais transmises.
- Documenter les resets, interruptions et checkpoints manquants : des differences
  de compteurs non comparables ne sont pas des mesures fiables de perte.
- Distinguer causes connues : horloge, IMU, file pleine, reseau, rejet, corruption ;
  les intervalles d'absence et trous de sequence seuls ne prouvent pas la cause.
  La sequence avance aussi pour les fenetres v2 et invalides.

## Comparaisons possibles et limites

Comparer les features et predictions diagnostiques entre archives et fenetres
datees de meme profil, avec stratification par device/session et contexte connu.
Les predictions du modele ne constituent pas une verite terrain. Les archives
lost/maintenance ou a historique de perte connu demandent un traitement distinct.

Ne pas attribuer une archive a une heure de la journee a partir de received_at :
un envoi differe peut survenir longtemps apres la mesure. L'heure de reception
permet d'etudier le transport, pas de prouver l'heure du comportement. Les analyses
horaires d'acquisition exigent des ancrages UTC independants et une incertitude
quantifiee ; leur reconstruction auditee reste hors du lot technique actuel.

Le couvert arbore, les pratiques de paturage et la meteo doivent etre observes
independamment avec une provenance defendable. Ne pas deduire une localisation
fiable de l'absence de GPS, ni une ferme d'acquisition du snapshot de reception.

Rapporter les distributions, effectifs, incertitudes, limites d'observation et
analyses de sensibilite pertinentes. Une correlation observable ne prouve pas
un mecanisme MNAR ; l'archive ne suffit pas a identifier ou corriger ce mecanisme.
La motivation bibliographique et sa portee figurent a la fin du plan d'implementation.

## Livrable futur

Un rapport reproductible avec definitions des cohortes/denominateurs, provenance,
versions de firmware et de modele, exclusions et limites. Aucun reetiquetage,
reentrainement ou reintegration automatique dans les resumes journaliers sans
protocole scientifique et validation distincts.

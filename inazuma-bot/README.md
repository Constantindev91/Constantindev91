# ⚽ INAZUMA BOT

Un bot Discord de gestion d'équipe façon *Soccer Guru*, mais 100% univers **Inazuma Eleven** :
réclame des joueurs toutes les 30 minutes, compose ton équipe, achète des techniques/tactiques/coachs,
échange et vends des joueurs sur le marché des transferts, et affronte les autres membres du serveur
en 1v1 classé.

Aucune image officielle de la licence n'est utilisée : chaque carte est **générée à la volée**
(dégradé de couleur par rareté, barres de stats, étoiles) via Pillow, donc le bot fonctionne
immédiatement sans aucun asset externe. Le contenu (noms de joueurs, techniques, tactiques, coachs,
stats, textes de flaveur) est une base de données originale inspirée de la licence.

## Installation

```bash
cd inazuma-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# édite .env et renseigne DISCORD_TOKEN (et éventuellement DEV_GUILD_ID pour tester sur un seul serveur)
python3 main.py
```

Le bot crée automatiquement `inazuma.db` (SQLite) au premier lancement et charge tout le contenu
depuis `data/*.json`. Relancer le bot après avoir édité ces fichiers JSON met à jour le contenu de
référence (joueurs/techniques/tactiques/coachs) sans toucher aux données des joueurs (inventaires,
argent, équipes...).

### Créer le bot sur Discord

1. https://discord.com/developers/applications → New Application.
2. Onglet **Bot** → Reset Token → colle-le dans `.env` comme `DISCORD_TOKEN`.
3. Onglet **OAuth2 → URL Generator** → coche `bot` + `applications.commands`, permissions minimales :
   Send Messages, Embed Links, Attach Files, Use Slash Commands.
4. Invite le bot sur ton serveur avec le lien généré.
5. Pour tester instantanément (sync immédiat au lieu de ~1h) : mets l'ID de ton serveur dans
   `DEV_GUILD_ID` dans `.env`.

## Contenu du jeu

- **130 joueurs** couvrant toute la licence (Inazuma Eleven original, GO, Chrono Stone, Galaxy,
  Ares, Orion), répartis en 5 niveaux de rareté (⭐ à ⭐⭐⭐⭐⭐).
- **57 techniques (hissatsu)** : tirs, dribbles, blocages et parades.
- **18 tactiques d'équipe** et **12 coachs**, chacun avec des bonus de stats.
- Système économique en **Kizuna Points (KP)**.

Tout ce contenu vit dans `data/*.json` — tu peux l'étendre librement (ajouter des joueurs, corriger
des stats, etc.) en respectant le schéma existant, sans toucher au code.

## Commandes principales

Tape `/help` dans Discord pour la liste complète et à jour, catégorie par catégorie. Aperçu :

| Catégorie | Commandes |
|---|---|
| Profil | `/start`, `/profile`, `/daily` |
| Claim & Collection | `/claim`, `/collection`, `/card`, `/sell`, `/lock`, `/unlock` |
| Équipe | `/team view`, `/team formation`, `/team set`, `/team bench`, `/team equip`, `/team tactic`, `/team coach` |
| Boutique | `/shop techniques`, `/shop tactics`, `/shop coaches`, `/buy`, `/inventory` |
| Marché des transferts | `/market list`, `/market browse`, `/market buy`, `/market cancel`, `/market mine` |
| Échanges | `/trade propose`, `/trade cancel` |
| Combat & Ranked | `/battle challenge`, `/battle history` |
| Classements | `/leaderboard rank`, `/leaderboard rich`, `/leaderboard wins` |

## Architecture

```
main.py                 Point d'entrée, chargement des cogs, sync des commandes
config.py                Constantes de jeu (cooldowns, prix, formations, rangs...)
db/models.py              Modèles SQLAlchemy (données de référence + données utilisateur)
db/database.py            Moteur async + seed des données depuis data/*.json au démarrage
db/repository.py          Fonctions partagées (get-or-create user, équipe active, cooldowns)
utils/card_render.py      Génération d'image de carte (Pillow, sans assets externes)
utils/battle_engine.py    Calcul de puissance d'équipe + simulation de match
utils/pagination.py       Vue de pagination générique pour les listes
cogs/*.py                  Une cog par domaine fonctionnel (claim, team, market, battle...)
data/*.json                Base de données de contenu (joueurs, techniques, tactiques, coachs)
```

## Limites connues / pistes d'extension

- Pas d'images officielles (droits d'auteur) : les cartes sont générées graphiquement. Tu peux
  brancher tes propres visuels plus tard en ajoutant un champ `image_url` par entité et en modifiant
  `card_render.py` pour composer par-dessus une image de fond au lieu d'un dégradé.
- Pas de système de niveau/XP par joueur (les stats sont fixes par rareté) — facile à ajouter en
  stockant un `level` sur `UserCard` et en appliquant un multiplicateur dans les requêtes de puissance.
- Le roster de 130 joueurs couvre les personnages les plus emblématiques de chaque saison/équipe,
  pas la totalité des ~1000+ personnages de la licence — `data/players.json` est fait pour être
  étendu facilement (même schéma, nouvel objet dans le tableau).
- La simulation de combat est un modèle de rating (attaque vs défense + tirage façon Poisson), pas
  une simulation minute par minute — volontairement simple pour rester rapide et lisible en embed.

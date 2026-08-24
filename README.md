# agent-bons-plans

Bot qui surveille les promos Steam / Epic Games Store / GOG via
l'API [IsThereAnyDeal](https://isthereanydeal.com/) et envoie sur Telegram
un digest des réductions de **plus de 70%** et des jeux passés à **0€**,
sans jamais renvoyer deux fois la même offre.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

Édite ensuite `config.json` avec tes vraies valeurs (ce fichier est
ignoré par git, il ne doit jamais être commité) :

- `itad_api_key` : ta clé API IsThereAnyDeal (compte développeur sur
  [isthereanydeal.com](https://isthereanydeal.com/)).
- `telegram_bot_token` : le token donné par [@BotFather](https://t.me/BotFather)
  après `/newbot`.
- `telegram_chat_id` : voir ci-dessous.
- `itad_country` : code pays ISO 2 lettres pour les prix (défaut `FR`).
- `channel_link` *(optionnel)* : lien public de ton canal (ex: `https://t.me/mon_canal`).
  Si rempli, un footer « Partage ce canal » apparaît en bas de chaque message.
- `affiliate_links` *(optionnel)* : liste de `{"label": ..., "url": ...}`.
  Si rempli, un footer « Plus de deals » avec tes liens apparaît en bas de
  chaque message. **Ne sert que pour tes propres liens** (GOG, Fanatical,
  Instant Gaming...) — voir la section Monétisation plus bas, on n'a pas le
  droit de toucher aux liens fournis par IsThereAnyDeal eux-mêmes.

## Trouver ton `telegram_chat_id`

**Chat privé avec le bot :**
1. Envoie n'importe quel message à ton bot sur Telegram.
2. Ouvre `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`.
3. Récupère la valeur de `message.chat.id`.

**Canal Telegram :**
1. Ajoute le bot comme **administrateur** du canal (obligatoire pour poster).
2. Canal public (`@mon_canal`) : utilise directement `"@mon_canal"` comme
   `telegram_chat_id`, pas besoin d'ID numérique.
3. Canal privé : poste un message dans le canal, puis regarde
   `getUpdates` comme ci-dessus et cherche `channel_post.chat.id`
   (nombre négatif du type `-100...`).

## Utilisation

```bash
python3 bons_plans_bot.py
```

L'historique des offres déjà envoyées est stocké dans
`sent_offers.json` (créé automatiquement). Le supprimer réinitialise
les notifications.

## Monétisation

Les [conditions d'utilisation d'IsThereAnyDeal](https://github.com/IsThereAnyDeal/API/blob/master/TERMS_OF_SERVICE.md)
autorisent l'usage commercial si le canal est public, mais **interdisent
formellement de modifier les données fournies, y compris remplacer les
tags d'affiliation dans les URLs `itad.link`**. Impossible donc d'injecter
tes propres liens affiliés Steam/Epic/GOG dans les deals ITAD — ces liens
doivent rester intacts tels quels.

La voie compatible : avoir tes **propres** liens affiliés sur des boutiques
qui proposent un vrai programme, et les afficher en plus (footer
`affiliate_links` ci-dessus), pas à la place des liens ITAD :

- **GOG** — 6% des ventes nettes. Inscription sur [affiliate.gog.com](https://affiliate.gog.com/)
  ou par email à `affiliate@gog.com`.
- **Fanatical** — jusqu'à 12% de commission. Inscription sur [partners.fanatical.com](https://partners.fanatical.com).
- **Instant Gaming** — programme d'affiliation existant, inscription directement
  sur leur site ; taux de commission trouvés en ligne peu fiables/contradictoires,
  à vérifier toi-même une fois inscrit.

Steam n'a plus de programme d'affiliation accessible au public, et le
"Support-A-Creator" d'Epic demande à l'acheteur de saisir un code
manuellement au checkout — ni l'un ni l'autre ne fonctionne via un simple lien.

Ces programmes exigent une inscription (identité, site/canal à présenter) —
c'est une démarche à faire toi-même. Sans audience sur le canal, aucun de
ces leviers ne rapporte grand-chose de toute façon : la priorité reste de
faire grossir les abonnés avant d'optimiser la monétisation.

## Automatisation avec GitHub Actions (recommandé)

Le workflow [.github/workflows/bons-plans.yml](.github/workflows/bons-plans.yml)
exécute le bot 3 fois par jour (7h13, 13h13, 19h13 UTC, soit environ
9h/15h/21h heure de Paris en été) directement sur les serveurs GitHub —
pas besoin de laisser un ordinateur allumé.

**Prérequis :** le code doit être dans un repo GitHub (le dossier n'est pas
encore un dépôt git pour l'instant — dis-moi si tu veux que je m'en occupe).

### Ajouter les secrets dans GitHub

1. Va sur la page de ton repo sur GitHub.
2. **Settings** (⚙️, en haut du repo) → dans le menu de gauche, **Secrets and variables** → **Actions**.
3. Onglet **Secrets** → bouton **New repository secret**.
4. Crée ces 3 secrets un par un (nom exact à gauche, valeur à droite) :
   - `ITAD_API_KEY` → ta clé API IsThereAnyDeal
   - `TELEGRAM_BOT_TOKEN` → le token donné par BotFather
   - `TELEGRAM_CHAT_ID` → ton chat_id ou `@nom_de_canal`
5. Optionnel : `ITAD_COUNTRY` (défaut `FR` si absent) et `CHANNEL_LINK`
   fonctionnent aussi comme secrets si tu veux les activer en CI, même si
   ce ne sont pas des valeurs sensibles.

Ces valeurs sont chiffrées par GitHub, jamais visibles dans les logs du
workflow, et ne transitent jamais par le code source.

### Comment ça reste synchronisé (pas de doublons)

Chaque exécution GitHub Actions part d'un environnement neuf : sans rien
de spécial, le bot perdrait la mémoire des offres déjà envoyées à chaque
run et les renverrait en boucle. Le workflow contourne ça en recommitant
automatiquement `sent_offers.json` sur le repo après chaque exécution —
c'est pour ça que ce fichier n'est plus dans `.gitignore`. Le prochain run
repart du fichier à jour.

**À savoir :** GitHub désactive automatiquement les workflows planifiés
après 60 jours sans le moindre commit sur le repo. Avec 3 boutiques et le
filtre à 70%, il y a quasiment toujours une nouvelle offre à committer,
donc ce cas est très improbable — mais si le bot semble s'être arrêté
après une longue période calme, va dans l'onglet **Actions** du repo et
relance-le manuellement (bouton **Run workflow**, le workflow accepte
aussi ce déclenchement manuel).

## Automatisation en local (cron)

Alternative si tu préfères faire tourner ça sur ta propre machine plutôt
que sur GitHub :

```bash
crontab -e
```

```
0 */3 * * * cd /Users/hassancheaib/agent-bons-plans && .venv/bin/python3 bons_plans_bot.py >> bot.log 2>&1
```

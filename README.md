# World in 60 — chaîne d'actu internationale automatisée (en anglais)

Toutes les 30 minutes, **GitHub Actions** lance le bot gratuitement :

```
14 médias anglophones (RSS) ──► regroupement local : même événement vu par ≥ 2 médias ?
   ──► LLM open source gratuit (gpt-oss-120b) : tri "juicy" + score + choix du format
   ──► script en anglais ──► voix (Sam 🇺🇸 / Nina 🇬🇧) ──► photos libres ──► montage 1080×1920
   ──► YouTube Shorts · Instagram Reels · TikTok
Chaque soir 20:48 UTC ──► récap long 16:9 avec chapitres ──► YouTube
```

Pas de quota fixe : 8 grosses infos = 8 vidéos, journée calme = 0 vidéo (plafond de sécurité : 14/jour).

## Le montage : chaque vidéo change de plan à chaque réplique

Sam & Nina se renvoient la balle pendant 45 à 60 s, et **chaque réplique a son propre plan** :

| Plan | Ce qu'on voit |
|---|---|
| `desk` | Sam & Nina au plateau, l'écran derrière eux (accroche, réactions, échanges) |
| `photo` | photo plein écran qui zoome lentement + 1-4 mots-chocs |
| `stat` | un chiffre clé qui défile, avec sa légende |
| `points` | 2-3 points clés qui apparaissent un par un |
| `claim` | « ACCORDING TO BBC… » : ce que rapporte un média, avec attribution |
| `versus` | comparaison A vs B (avant/après, pays contre pays…) |
| `timeline` | chronologie des dates clés |
| `question` | interaction : question au public avec réponses A/B/C + « comment your answer » |

Hors plateau, le présentateur qui parle reste à l'écran dans un **médaillon** animé (bouche synchronisée),
et les deux apparaissent sur la question finale. Quatre transitions différentes alternent entre les plans.

Le LLM choisit les plans, puis le bot **vérifie le montage** avant le rendu :
- au moins 5 plans différents, jamais deux fois le même d'affilée ;
- 3 plans plateau maximum, Sam & Nina toujours visibles au moins une fois ;
- un chiffre affiché à l'écran doit figurer dans les dépêches, sinon le plan est remplacé ;
- pas de question au public sur un sujet grave : la vidéo se termine alors par un plan plateau sobre.

La question finale est aussi reprise dans la description pour faire réagir en commentaires.
Style : *fun but reliable* + pédagogique. Musique de fond originale générée par le bot.
Les anciens formats à style unique restent disponibles dans `config.yaml` (`formats.mode`).

## Le LLM gratuit

**gpt-oss-120b**, modèle open source (licence Apache 2.0), via deux API gratuites sans carte bancaire :
**Groq** en premier, **Cerebras** en relais si Groq est saturé. Le quota gratuit de Groq est d'environ
200 000 tokens/jour : le bot regroupe d'abord les dépêches lui-même et n'appelle le LLM que s'il y a du
nouveau, ce qui reste largement dedans.

## Installation (≈ 45 min, une seule fois)

### 1. Le dépôt GitHub
1. Crée un dépôt **public** sur GitHub (minutes Actions illimitées) et envoie-y tout ce dossier.
2. Onglet **Actions** → active les workflows si GitHub le demande.
3. **Settings → Actions → General → Workflow permissions** → coche *Read and write permissions*.

### 2. Les secrets (Settings → Secrets and variables → Actions → New repository secret)

| Secret | Où le trouver |
|---|---|
| `GROQ_API_KEY` | console.groq.com → API Keys (gratuit) |
| `CEREBRAS_API_KEY` | cloud.cerebras.ai → API Keys (gratuit, relais optionnel mais conseillé) |
| `PIXABAY_API_KEY` | pixabay.com/api/docs → la clé s'affiche une fois connecté (gratuit, optionnel) |
| `STATE_KEY` | sur ton PC : `python -m newsbot keygen` |
| `YOUTUBE_TOKEN_JSON` | étape 3 |
| `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID` | étape 4 |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_TOKEN_JSON` | étape 5 |

Les étapes 3 et 5 se font **une fois sur ton ordinateur** :
```bash
pip install -r requirements.txt
cp .env.example .env     # remplis TIKTOK_* et YOUTUBE_CLIENT_SECRETS
```

### 3. YouTube
1. console.cloud.google.com → nouveau projet → active **YouTube Data API v3**.
2. Écran de consentement OAuth (Externe) → **publie-le en Production** (sinon le token expire au bout de 7 jours).
3. Identifiants → ID client OAuth → **Application de bureau** → télécharge le JSON dans `secrets/youtube_client_secret.json`.
4. `python -m newsbot auth youtube` → connecte-toi avec la chaîne → copie le JSON affiché dans le secret `YOUTUBE_TOKEN_JSON`.

### 4. Instagram (compte **Professionnel ou Créateur**)
developers.facebook.com → crée une app → produit Instagram → *API avec connexion Instagram* → ajoute ton compte →
génère un token avec `instagram_business_content_publish`. Mets le token et l'ID du compte dans les secrets.
Le bot renouvelle le token tout seul (stocké chiffré).

### 5. TikTok
1. developers.tiktok.com → crée une app → **Login Kit** + **Content Posting API** (Direct Post).
2. Redirect URI : n'importe quelle page à toi, par ex. `https://TON-PSEUDO.github.io/TON-DEPOT/`.
3. `python -m newsbot auth tiktok` → autorise → colle l'URL de retour → copie le JSON affiché dans `TIKTOK_TOKEN_JSON`.
4. ⚠ Tant que TikTok n'a pas **audité** ton app, tout ce qui est posté par l'API reste **privé** (et le compte doit être privé).
   Demande l'audit dans le portail dès que les premières vidéos passent.

### 6. Premier test
Onglet **Actions → News run → Run workflow** :
- `demo` : rend la vidéo de démo (tous les plans) avec les vraies voix, sans rien publier
- `preview` : un vrai passage sur l'actu du moment, **sans publier**
- `run` : un passage réel avec publication

Les vidéos produites sont téléchargeables 3 jours dans chaque exécution → **Artifacts**.
Ensuite tu n'as plus rien à faire : le planning tourne tout seul.

## Réglages (`config.yaml`)

- `channel` : nom, handle, slogan
- `selection.min_score` : plus haut = plus sélectif · `max_videos_per_day` : plafond
- `characters` : prénoms et voix de Sam & Nina (liste des voix : `edge-tts --list-voices`)
- `sources` : flux RSS (anglophones, pour que le regroupement fonctionne)
- `music.volume` / `music.enabled` · `theme` : couleurs
- `platforms.youtube.privacy: private` pour une période de rodage

## Garde-fous intégrés

- **Recoupement obligatoire** : une info vue par un seul média n'est jamais traitée.
- **Factuel** : le LLM ne peut utiliser que les faits des dépêches, réécrits avec ses mots, et attribue les infos sensibles.
- **Images libres** uniquement (Pixabay) ou fonds générés, jamais les photos des médias.
- **Transparence IA** : mention à l'écran, `containsSyntheticMedia` (YouTube), `is_aigc` (TikTok).
- **Anti-doublon 48 h**, plateformes indépendantes (une panne n'arrête pas les autres), jamais deux passages en même temps.
- **Mémoire** sur la branche `state` (une seule version, l'historique ne grossit pas) ; les tokens y sont **chiffrés**.

## À savoir

- **Monétisation YouTube** : YouTube démonétise le contenu produit en masse sans valeur ajoutée. Sam & Nina donnent une
  identité ; ajoute un peu de toi (réponses aux commentaires, une intro perso de temps en temps).
- **C'est ta chaîne qui publie** : jette un œil aux vidéos chaque jour au début.
- GitHub met en pause les tâches planifiées d'un dépôt public après **60 jours sans activité** : il t'envoie un mail,
  un clic suffit pour relancer (ou fais un petit commit de temps en temps).
- Les horaires GitHub sont « au mieux » : un passage peut partir avec quelques minutes de retard.
- Les voix utilisent le service gratuit de Microsoft Edge (edge-tts) : s'il devient indisponible, les vidéos échouent proprement et le passage suivant réessaie.

## Arborescence

```
newsbot/
  fetch.py     RSS                 cluster.py  regroupement local (0 token)
  curate.py    sélection (LLM)     writer.py   scripts anglais (LLM)
  llm.py       routeur Groq/Cerebras            tts.py      voix + timings mot à mot
  visuals.py   photos Pixabay       music.py    jingle original
  pipeline.py  un passage complet  recap.py    récap 16:9 du soir
  vault.py     tokens chiffrés     render/     moteur vidéo (anchors.py = Sam & Nina)
  publish/     youtube.py · instagram.py · tiktok.py
.github/workflows/  newsbot.yml (toutes les 30 min) · recap.yml (chaque soir)
deploy/state.sh     sauvegarde/restauration de la mémoire du bot
```

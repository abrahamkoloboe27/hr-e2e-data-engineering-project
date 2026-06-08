# HR Synthetic Data Engineering Project

Générateur de données synthétiques RH réalistes pour une entreprise internationale, avec insertion batch MongoDB Atlas, CLI configurable, seed de reproductibilité, et architecture modulaire Python.

## Stack

- Python 3.11+
- `uv` (gestion du projet et dépendances)
- `faker` (génération de données réalistes)
- MongoDB Atlas (`pymongo`)
- `python-dotenv`
- `tqdm`

## Structure

```text
src/
├── config/
│   └── settings.py
├── generators/
│   ├── base.py
│   └── hr_pipeline.py
├── db/
│   └── mongo.py
├── models/
│   └── reference_data.py
├── utils/
│   ├── ids.py
│   └── logging_utils.py
└── main.py
tests/
```

## Installation (uv)

```bash
uv sync
```

Pour les tests :

```bash
uv sync --extra dev
```

## Configuration `.env`

Copier `.env.example` vers `.env` puis renseigner vos valeurs MongoDB Atlas.

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority
MONGODB_DATABASE=hr_synthetic
MONGODB_TIMEOUT_MS=20000
```

## Exécution

```bash
python -m src.main --employees 500 --batch-size 5000 --seed 42
```

Exemple grand volume :

```bash
python -m src.main --employees 100000 --batch-size 5000 --seed 42 --retry-count 5
```

Mode reprise :

```bash
python -m src.main --employees 500000 --batch-size 5000 --resume
```

## Collections générées

Ordre de génération respecté :

1. offices
2. departments
3. positions
4. employees
5. teams
6. recruitments
7. payrolls
8. absences
9. trainings
10. training_participations
11. performance_reviews
12. promotions
13. engagement_surveys
14. employee_assets
15. exits

Chaque collection contient :
- `_id` MongoDB
- `unique_id` métier

## Réalisme métier implémenté

- Répartition hiérarchique (beaucoup de juniors, peu de directeurs)
- Salaires cohérents selon niveau, poste, pays
- Turnover différencié par département
- Absences réalistes (congés majoritaires)
- Performance à distribution gaussienne
- Promotions rares, corrélées aux évaluations
- Formations plus fréquentes dans certains métiers
- Engagement corrélé à performance et ancienneté
- Recrutements avec taux d’échec réaliste
- Cohérence temporelle des dates

## Batch processing obligatoire

Pipeline implémenté :
1. génération d’un batch
2. validation implicite du batch
3. insertion MongoDB via `insert_many(..., ordered=False)`
4. libération mémoire
5. batch suivant

## Suivi d’avancement

- `tqdm` pour les progress bars
- logs détaillés par batch
- documents générés et insérés
- temps total d’exécution
- vitesse documents/seconde

## Index MongoDB créés automatiquement

- `unique_id` (unique)
- `employee_unique_id`
- `department_unique_id`
- `team_unique_id`
- `manager_unique_id`
- `position_unique_id`

## Qualité du code

- architecture modulaire
- typage Python
- gestion d’erreurs et retry insertion
- code extensible avec `BaseGenerator.generate_batch(batch_size)`

## Important sécurité

- aucun credential hardcodé
- usage obligatoire de variables d’environnement
- `.env` non versionné (utiliser `.env.example`)

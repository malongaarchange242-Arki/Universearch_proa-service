"""
Module de scoring des filières par rapport aux domaines PROA.
Calcule la compatibilité entre une filière de formation et les centres d'intérêt de l'utilisateur.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging
import json

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FiliereScore:
    """Représente le score d'une filière par rapport aux domaines PROA"""
    filiere_id: str
    filiere_name: str
    cluster: str              # Cluster PROA: "informatique", "business", "droit", etc.
    duration_years: float     # Durée de la formation en années
    score: float              # Score de compatibilité (0-1)
    domain_matches: Dict[str, float]  # Domaines PROA matchés avec leur poids
    top_domains: List[str]    # Top 3 domaines PROA associés
    domains_list: List[str]   # Tous les domaines PROA de la filière
    compatibility_level: str  # "high", "medium", "low"


class FiliereEngineScore:
    """
    Moteur de calcul de scores pour les filières.
    Détermine la compatibilité entre les filières d'éducation et les domaines PROA d'un utilisateur.
    """
    
    # ========================================================================
    # MAPPING DOMAINE_ID → CLUSTER PROA
    # ========================================================================
    # Ces UUIDs viennent de ta table 'domaines'
    # À COMPLÉTER AVEC TES VRAIS UUIDS !
    
    DOMAINE_ID_TO_CLUSTER = {
        # Informatique & Data
        "ebd8c748-f0ba-46d2-be22-5414d1f69801": "informatique",
        "f32e03b6-631d-40ce-9643-836dd766b566": "informatique",
        
        # Ingénierie & Industrie
        "726004cb-b65d-463e-80fe-2bb93b1a9fae": "engineering",
        "52650527-87b4-4782-bf92-617fb384bf39": "engineering",
        "00df4bf8-f214-4e8e-86de-80342d694529": "engineering",
        
        # Business & Gestion
        "8eb8b4d1-144a-472a-a5d7-1a32efb049c5": "business",
        "c756ec28-852d-438c-b01a-75dfbeb23705": "business",
        "9a4a5492-9402-4be0-802a-3969dd1c8228": "business",
        "6612f1d7-0200-4c29-ada6-26075cc80897": "business",
        
        # Droit
        "978620ba-d64e-4830-8e49-cc7dc2cd716e": "droit",
        
        # Sciences Humaines & Sociales
        "091d7554-789d-4732-857c-783fcebeab98": "social",
        
        # Géosciences & Mines
        "91720f18-806a-4db6-bff2-7f59da142bd8": "geoscience",
        
        # Environnement
        "921c5973-57c2-4e02-8f95-3b8137408c86": "geoscience",
        
        # Agriculture & Agroalimentaire
        "2fe00ff3-cc68-431f-8ba7-27962226ad08": "agriculture",
    }
    
    # ========================================================================
    # MOTS-CLÉS PAR CLUSTER (FALLBACK SI PAS DE DOMAINE_ID)
    # ========================================================================
    
    CLUSTER_KEYWORDS = {
        "informatique": [
            "data", "logiciel", "informatique", "programmation", "dev", "development",
            "ia", "intelligence artificielle", "cyber", "cybersecurite", "securite",
            "reseau", "telecom", "web", "mobile", "cloud", "devops", "fullstack",
            "backend", "frontend", "base de donnee", "sql", "python", "java", "javascript"
        ],
        "engineering": [
            "genie", "ingenierie", "engineering", "electrique", "electronique",
            "mecanique", "industriel", "civil", "btp", "batiment", "construction",
            "automatisme", "robotique", "petrol", "petrolier", "procede", "chimie",
            "materiaux", "thermique", "energetique", "aerospatial", "aeronautique"
        ],
        "business": [
            "finance", "gestion", "marketing", "commerce", "comptabilite", "rh",
            "ressources humaines", "logistique", "transport", "supply chain", "achat",
            "vente", "management", "administration", "economie", "banque", "assurance",
            "audit", "controle de gestion", "business", "entrepreneuriat"
        ],
        "droit": [
            "droit", "juridique", "penal", "justice", "avocat", "notaire", "judiciaire",
            "droit prive", "droit public", "droit des affaires", "droit social",
            "droit international", "science criminelle", "contentieux"
        ],
        "social": [
            "communication", "science politique", "diplomatie", "langues", "medecine",
            "sante", "social", "sociologie", "psychologie", "education", "enseignement",
            "professorat", "pedagogie", "assistant medical", "paramedical", "infirmier",
            "diplomate", "relations internationales"
        ],
        "geoscience": [
            "mine", "geologie", "geophysique", "geoscience", "carriere", "topographe",
            "geometre", "gis", "systeme d'information geographique", "cartographie",
            "geotechnique", "hydrogeologie", "ressources naturelles"
        ],
        "agriculture": [
            "agro", "agricole", "alimentaire", "agroalimentaire", "agronomie",
            "viticulture", "oenologie", "elevage", "veterinaire", "horticulture",
            "environnement", "developpement durable", "qse", "hse"
        ],
        "arts_design": [
            "architecture", "design", "urbanisme", "art", "creation", "multimedia",
            "graphisme", "animation 3d", "game design", "audiovisuel", "cinema"
        ]
    }
    
    def __init__(self, db_connection):
        """
        Initialise le moteur de scoring.
        
        Args:
            db_connection: Connexion à la base de données (psycopg2, sqlite3, etc.)
        """
        self.db = db_connection
        self.cursor = db_connection.cursor()
        logger.info("FiliereEngineScore initialisé")
        
        # Créer la table des scores si elle n'existe pas
        self._create_scores_table()
    
    # ========================================================================
    # MÉTHODES DE BASE DE DONNÉES
    # ========================================================================
    
    def _create_scores_table(self):
        """
        Crée la table matcheur_filiere_scores si elle n'existe pas.
        Cette table stocke les résultats de scoring pour chaque utilisateur/filière.
        """
        # Version PostgreSQL
        query_pg = """
        CREATE TABLE IF NOT EXISTS matcheur_filiere_scores (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            session_id VARCHAR(255),
            filiere_id VARCHAR(255) NOT NULL,
            filiere_name VARCHAR(500),
            cluster VARCHAR(100),
            score DECIMAL(5,4),
            compatibility_level VARCHAR(20),
            duration_years DECIMAL(4,2),
            user_domains JSON,
            matched_domains JSON,
            top_domains JSON,
            all_domains JSON,
            score_details JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Index pour les recherches fréquentes
            INDEX idx_user_filiere (user_id, filiere_id),
            INDEX idx_session (session_id),
            INDEX idx_score (score DESC),
            INDEX idx_created (created_at DESC)
        );
        """
        
        # Version SQLite (simplifiée)
        query_sqlite = """
        CREATE TABLE IF NOT EXISTS matcheur_filiere_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(255) NOT NULL,
            session_id VARCHAR(255),
            filiere_id VARCHAR(255) NOT NULL,
            filiere_name VARCHAR(500),
            cluster VARCHAR(100),
            score DECIMAL(5,4),
            compatibility_level VARCHAR(20),
            duration_years DECIMAL(4,2),
            user_domains TEXT,
            matched_domains TEXT,
            top_domains TEXT,
            all_domains TEXT,
            score_details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        try:
            # Détecter le type de base de données
            db_type = str(type(self.db)).lower()
            
            if "sqlite" in db_type:
                self.cursor.execute(query_sqlite)
                logger.info("Table matcheur_filiere_scores créée/vérifiée (SQLite)")
            else:
                self.cursor.execute(query_pg)
                logger.info("Table matcheur_filiere_scores créée/vérifiée (PostgreSQL)")
            
            self.db.commit()
        except Exception as e:
            logger.warning(f"Erreur lors de la création de la table: {e}")
            logger.info("La table existe peut-être déjà")
    
    def _save_score_to_db(self, user_id: str, session_id: str, filiere_score: FiliereScore, 
                          user_domains: List[str], score_details: Dict[str, Any]):
        """
        Sauvegarde un score individuel dans la base de données.
        
        Args:
            user_id: Identifiant de l'utilisateur
            session_id: Identifiant de session (peut être None)
            filiere_score: Objet FiliereScore à sauvegarder
            user_domains: Liste des domaines de l'utilisateur
            score_details: Détails supplémentaires du calcul
        """
        # Convertir les dictionnaires/listes en JSON
        user_domains_json = json.dumps(user_domains)
        matched_domains_json = json.dumps(filiere_score.domain_matches)
        top_domains_json = json.dumps(filiere_score.top_domains)
        all_domains_json = json.dumps(filiere_score.domains_list)
        score_details_json = json.dumps(score_details)
        
        # Version PostgreSQL
        query_pg = """
        INSERT INTO matcheur_filiere_scores 
        (user_id, session_id, filiere_id, filiere_name, cluster, score, 
         compatibility_level, duration_years, user_domains, matched_domains, 
         top_domains, all_domains, score_details, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, filiere_id) 
        DO UPDATE SET 
            score = EXCLUDED.score,
            compatibility_level = EXCLUDED.compatibility_level,
            matched_domains = EXCLUDED.matched_domains,
            top_domains = EXCLUDED.top_domains,
            updated_at = EXCLUDED.updated_at
        """
        
        # Version SQLite (sans ON CONFLICT)
        query_sqlite = """
        INSERT OR REPLACE INTO matcheur_filiere_scores 
        (user_id, session_id, filiere_id, filiere_name, cluster, score, 
         compatibility_level, duration_years, user_domains, matched_domains, 
         top_domains, all_domains, score_details, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                COALESCE((SELECT created_at FROM matcheur_filiere_scores 
                          WHERE user_id = %s AND filiere_id = %s), %s),
                %s)
        """
        
        now = datetime.now()
        
        try:
            db_type = str(type(self.db)).lower()
            
            if "sqlite" in db_type:
                # SQLite: besoin de plus de paramètres
                self.cursor.execute(query_sqlite, (
                    user_id, session_id, filiere_score.filiere_id, 
                    filiere_score.filiere_name, filiere_score.cluster,
                    filiere_score.score, filiere_score.compatibility_level,
                    filiere_score.duration_years, user_domains_json,
                    matched_domains_json, top_domains_json, all_domains_json,
                    score_details_json, user_id, filiere_score.filiere_id, now, now
                ))
            else:
                # PostgreSQL
                self.cursor.execute(query_pg, (
                    user_id, session_id, filiere_score.filiere_id,
                    filiere_score.filiere_name, filiere_score.cluster,
                    filiere_score.score, filiere_score.compatibility_level,
                    filiere_score.duration_years, user_domains_json,
                    matched_domains_json, top_domains_json, all_domains_json,
                    score_details_json, now, now
                ))
            
            self.db.commit()
            logger.debug(f"Score sauvegardé pour user={user_id}, filiere={filiere_score.filiere_name[:30]}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du score: {e}")
    
    def save_all_scores(self, user_id: str, scores: List[FiliereScore], 
                        user_domains: List[str], session_id: Optional[str] = None):
        """
        Sauvegarde tous les scores d'un utilisateur en base de données.
        
        Args:
            user_id: Identifiant de l'utilisateur
            scores: Liste des FiliereScore à sauvegarder
            user_domains: Liste des domaines de l'utilisateur
            session_id: Identifiant de session (optionnel)
        """
        logger.info(f"Sauvegarde de {len(scores)} scores pour l'utilisateur {user_id}")
        
        for i, score in enumerate(scores):
            # Créer des détails supplémentaires pour chaque score
            score_details = {
                "rank": i + 1,
                "percentile": (1 - i/len(scores)) * 100 if scores else 0,
                "total_filieres": len(scores)
            }
            
            self._save_score_to_db(user_id, session_id, score, user_domains, score_details)
        
        logger.info(f"Sauvegarde terminée pour {user_id}")
    
    # ========================================================================
    # MÉTHODES DE DÉTERMINATION DU CLUSTER
    # ========================================================================
    
    def _determine_cluster(self, filiere_info: Dict[str, Any]) -> str:
        """
        Détermine le cluster PROA à partir des données de la filière.
        
        Stratégie à 3 niveaux:
        1. Mapping direct domaine_id → cluster (le plus précis)
        2. Analyse du nom/slug par mots-clés (fallback)
        3. Retourne "unknown" (dernier recours)
        
        Args:
            filiere_info: Dictionnaire contenant domaine_id, filiere_name, slug
            
        Returns:
            Nom du cluster: "informatique", "business", "droit", "engineering", etc.
        """
        # ====================================================================
        # NIVEAU 1: Mapping direct par domaine_id
        # ====================================================================
        domaine_id = filiere_info.get("domaine_id")
        if domaine_id:
            # Nettoyer l'UUID (enlever les tirets si besoin)
            domaine_id_clean = str(domaine_id).strip()
            
            if domaine_id_clean in self.DOMAINE_ID_TO_CLUSTER:
                cluster = self.DOMAINE_ID_TO_CLUSTER[domaine_id_clean]
                logger.debug(f"[DIRECT MAP] domaine_id={domaine_id_clean[:8]}... → cluster={cluster}")
                return cluster
            else:
                logger.debug(f"[UNKNOWN ID] domaine_id={domaine_id_clean[:8]}... non trouvé dans mapping")
        
        # ====================================================================
        # NIVEAU 2: Analyse par mots-clés
        # ====================================================================
        filiere_name = filiere_info.get("filiere_name", "").lower()
        slug = filiere_info.get("slug", "").lower()
        
        # Combiner nom et slug pour plus de texte à analyser
        # Remplacer les tirets par des espaces
        combined = f"{filiere_name} {slug}".replace("-", " ")
        
        # Parcourir tous les clusters et leurs mots-clés
        for cluster, keywords in self.CLUSTER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in combined:
                    logger.debug(f"[NLP FALLBACK] Mot-clé '{keyword}' trouvé → cluster={cluster}")
                    logger.debug(f"  Texte analysé: {combined[:100]}...")
                    return cluster
        
        # ====================================================================
        # NIVEAU 3: Unknown (aucune correspondance trouvée)
        # ====================================================================
        logger.warning(f"[UNKNOWN] Impossible de déterminer le cluster pour: "
                      f"filiere_name={filiere_info.get('filiere_name')}, "
                      f"domaine_id={domaine_id}")
        return "unknown"
    
    # ========================================================================
    # MÉTHODES DE RÉCUPÉRATION DES DONNÉES
    # ========================================================================
    
    def _get_filiere_proa_domains(self, filiere_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les domaines PROA associés à une filière.
        
        Args:
            filiere_id: Identifiant de la filière
            
        Returns:
            Liste des domaines PROA avec leurs infos
        """
        query = """
            SELECT 
                mpd.proa_domain_id,
                pd.domain_name,
                pd.cluster,
                mpd.weight
            FROM matcheur_proa_domains mpd
            JOIN proa_domains pd ON mpd.proa_domain_id = pd.id
            WHERE mpd.filiere_id = %s
            ORDER BY mpd.weight DESC
        """
        
        try:
            self.cursor.execute(query, (filiere_id,))
            results = self.cursor.fetchall()
            
            domains = []
            for row in results:
                domains.append({
                    "proa_domain_id": row[0],
                    "domain_name": row[1],
                    "cluster": row[2],
                    "weight": row[3] if row[3] is not None else 1.0
                })
            
            return domains
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des domaines PROA pour filiere_id={filiere_id}: {e}")
            return []
    
    # ========================================================================
    # MÉTHODE PRINCIPALE DE CALCUL DES SCORES
    # ========================================================================
    
    def compute_filiere_scores(self, user_domains: List[str]) -> List[FiliereScore]:
        """
        Calcule les scores de compatibilité pour toutes les filières.
        
        Args:
            user_domains: Liste des domaines PROA sélectionnés par l'utilisateur
                         (ex: ["data_science", "machine_learning", "python"])
            
        Returns:
            Liste de FiliereScore triée par score décroissant
        """
        if not user_domains:
            logger.warning("Aucun domaine utilisateur fourni, retour d'une liste vide")
            return []
        
        logger.info(f"Calcul des scores pour {len(user_domains)} domaines utilisateur: {user_domains}")
        
        # Récupérer toutes les filières
        query = """
            SELECT 
                filiere_id,
                filiere_name,
                slug,
                domaine_id,
                sous_domaine_id,
                duree_ans
            FROM filieres
            WHERE actif = 1 OR actif IS NULL
            ORDER BY filiere_name
        """
        
        try:
            self.cursor.execute(query)
            filieres = self.cursor.fetchall()
            logger.info(f"Récupération de {len(filieres)} filières actives")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des filières: {e}")
            return []
        
        scores = []
        
        for filiere in filieres:
            filiere_id = filiere[0]
            filiere_name = filiere[1]
            slug = filiere[2]
            domaine_id = filiere[3]
            sous_domaine_id = filiere[4]
            duree_ans = filiere[5] if filiere[5] is not None else 3.0
            
            # ================================================================
            # ÉTAPE 1: Déterminer le cluster PROA de la filière
            # ================================================================
            filiere_info = {
                "domaine_id": domaine_id,
                "sous_domaine_id": sous_domaine_id,
                "filiere_name": filiere_name,
                "slug": slug
            }
            cluster = self._determine_cluster(filiere_info)
            
            # ================================================================
            # ÉTAPE 2: Récupérer les domaines PROA associés à la filière
            # ================================================================
            domain_mappings = self._get_filiere_proa_domains(filiere_id)
            domains_list = [dm.get("domain_name", "") for dm in domain_mappings]
            
            # ================================================================
            # ÉTAPE 3: Calculer les matchs avec les domaines de l'utilisateur
            # ================================================================
            domain_matches = {}
            total_weighted_score = 0.0
            total_possible_weight = 0.0
            
            for user_domain in user_domains:
                # Chercher si ce domaine est dans les domaines de la filière
                matched = False
                for dm in domain_mappings:
                    if dm["domain_name"] == user_domain:
                        weight = dm["weight"]
                        domain_matches[user_domain] = weight
                        total_weighted_score += weight
                        matched = True
                        break
                
                if not matched:
                    domain_matches[user_domain] = 0.0
                
                # Poids maximum possible pour ce domaine
                total_possible_weight += 1.0  # Chaque domaine utilisateur a un poids max de 1
            
            # Normaliser le score entre 0 et 1
            normalized_score = total_weighted_score / total_possible_weight if total_possible_weight > 0 else 0.0
            
            # ================================================================
            # ÉTAPE 4: Déterminer le niveau de compatibilité
            # ================================================================
            if normalized_score >= 0.7:
                compatibility = "high"
            elif normalized_score >= 0.4:
                compatibility = "medium"
            else:
                compatibility = "low"
            
            # ================================================================
            # ÉTAPE 5: Extraire le top 3 des domaines matchés
            # ================================================================
            top_domains = sorted(
                [(domain, weight) for domain, weight in domain_matches.items() if weight > 0],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            top_domains_list = [d[0] for d in top_domains]
            
            # ================================================================
            # ÉTAPE 6: Créer l'objet FiliereScore
            # ================================================================
            filiere_score = FiliereScore(
                filiere_id=filiere_id,
                filiere_name=filiere_name,
                cluster=cluster,                    # ← DÉTERMINÉ DYNAMIQUEMENT
                duration_years=float(duree_ans),
                score=round(normalized_score, 4),
                domain_matches=domain_matches,
                top_domains=top_domains_list,
                domains_list=domains_list,
                compatibility_level=compatibility
            )
            
            scores.append(filiere_score)
            
            # Log pour debug (optionnel)
            if normalized_score > 0:
                logger.debug(f"Score={normalized_score:.2f} | Cluster={cluster} | {filiere_name[:50]}")
        
        # Trier par score décroissant
        scores.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"Calcul terminé: {len(scores)} filières scorées")
        logger.info(f"  - High compatibility: {len([s for s in scores if s.compatibility_level == 'high'])}")
        logger.info(f"  - Medium compatibility: {len([s for s in scores if s.compatibility_level == 'medium'])}")
        logger.info(f"  - Low compatibility: {len([s for s in scores if s.compatibility_level == 'low'])}")
        
        return scores
    
    # ========================================================================
    # MÉTHODES DE RECHERCHE ET FILTRAGE
    # ========================================================================
    
    def get_top_filieres(self, user_domains: List[str], limit: int = 10) -> List[FiliereScore]:
        """
        Retourne les meilleures filières pour l'utilisateur.
        
        Args:
            user_domains: Domaines PROA de l'utilisateur
            limit: Nombre maximum de filières à retourner
            
        Returns:
            Liste des meilleures filières (limitée)
        """
        all_scores = self.compute_filiere_scores(user_domains)
        return all_scores[:limit]
    
    def get_filieres_by_cluster(self, user_domains: List[str], cluster: str) -> List[FiliereScore]:
        """
        Retourne les filières d'un cluster spécifique.
        
        Args:
            user_domains: Domaines PROA de l'utilisateur
            cluster: Nom du cluster ("informatique", "business", etc.)
            
        Returns:
            Liste des filières du cluster triées par score
        """
        all_scores = self.compute_filiere_scores(user_domains)
        filtered = [f for f in all_scores if f.cluster == cluster]
        return filtered
    
    def get_cluster_stats(self, user_domains: List[str]) -> Dict[str, Any]:
        """
        Calcule des statistiques par cluster pour l'utilisateur.
        
        Args:
            user_domains: Domaines PROA de l'utilisateur
            
        Returns:
            Statistiques agrégées par cluster
        """
        all_scores = self.compute_filiere_scores(user_domains)
        
        stats = {}
        for score in all_scores:
            if score.cluster not in stats:
                stats[score.cluster] = {
                    "count": 0,
                    "total_score": 0,
                    "avg_score": 0,
                    "high_count": 0,
                    "medium_count": 0,
                    "low_count": 0,
                    "top_filieres": []
                }
            
            stats[score.cluster]["count"] += 1
            stats[score.cluster]["total_score"] += score.score
            
            if score.compatibility_level == "high":
                stats[score.cluster]["high_count"] += 1
            elif score.compatibility_level == "medium":
                stats[score.cluster]["medium_count"] += 1
            else:
                stats[score.cluster]["low_count"] += 1
            
            # Garder le top 3 des filières de ce cluster
            if len(stats[score.cluster]["top_filieres"]) < 3:
                stats[score.cluster]["top_filieres"].append({
                    "name": score.filiere_name,
                    "score": score.score
                })
        
        # Calculer les moyennes et trier
        for cluster in stats:
            stats[cluster]["avg_score"] = round(
                stats[cluster]["total_score"] / stats[cluster]["count"], 4
            )
            stats[cluster]["top_filieres"] = sorted(
                stats[cluster]["top_filieres"],
                key=lambda x: x["score"],
                reverse=True
            )
        
        return stats
    
    # ========================================================================
    # MÉTHODES DE RÉCUPÉRATION DES SCORES SAUVEGARDÉS
    # ========================================================================
    
    def get_user_scores(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Récupère les scores précédemment calculés pour un utilisateur.
        
        Args:
            user_id: Identifiant de l'utilisateur
            limit: Nombre maximum de scores à récupérer
            
        Returns:
            Liste des scores sauvegardés
        """
        query = """
            SELECT 
                filiere_id, filiere_name, cluster, score, 
                compatibility_level, duration_years, user_domains,
                matched_domains, top_domains, created_at
            FROM matcheur_filiere_scores
            WHERE user_id = %s
            ORDER BY score DESC
            LIMIT %s
        """
        
        try:
            self.cursor.execute(query, (user_id, limit))
            results = self.cursor.fetchall()
            
            scores = []
            for row in results:
                scores.append({
                    "filiere_id": row[0],
                    "filiere_name": row[1],
                    "cluster": row[2],
                    "score": float(row[3]),
                    "compatibility_level": row[4],
                    "duration_years": float(row[5]),
                    "user_domains": json.loads(row[6]) if row[6] else [],
                    "matched_domains": json.loads(row[7]) if row[7] else {},
                    "top_domains": json.loads(row[8]) if row[8] else [],
                    "created_at": row[9]
                })
            
            return scores
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des scores: {e}")
            return []
    
    def get_user_best_filieres(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Récupère les meilleures filières pour un utilisateur (top scores).
        
        Args:
            user_id: Identifiant de l'utilisateur
            limit: Nombre maximum de filières
            
        Returns:
            Liste des meilleures filières
        """
        return self.get_user_scores(user_id, limit)


# ============================================================================
# FONCTION D'UTILISATION SIMPLE (POUR TESTS)
# ============================================================================

def test_filiere_scoring():
    """
    Fonction de test pour vérifier que tout fonctionne.
    """
    import sqlite3
    
    # Créer une connexion de test (remplace par ta vraie connexion)
    conn = sqlite3.connect(":memory:")  # Base temporaire en mémoire
    cursor = conn.cursor()
    
    # Créer une table de test simplifiée
    cursor.execute("""
        CREATE TABLE filieres (
            filiere_id TEXT PRIMARY KEY,
            filiere_name TEXT,
            slug TEXT,
            domaine_id TEXT,
            sous_domaine_id TEXT,
            duree_ans REAL,
            actif INTEGER
        )
    """)
    
    cursor.execute("""
        CREATE TABLE proa_domains (
            id TEXT PRIMARY KEY,
            domain_name TEXT,
            cluster TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE matcheur_proa_domains (
            filiere_id TEXT,
            proa_domain_id TEXT,
            weight REAL
        )
    """)
    
    # Insérer des données de test
    cursor.execute("""
        INSERT INTO filieres VALUES 
        ('f1', 'Master Data Science', 'master-data-science', 'ebd8c748-f0ba-46d2-be22-5414d1f69801', NULL, 2.0, 1),
        ('f2', 'MBA Finance', 'mba-finance', '8eb8b4d1-144a-472a-a5d7-1a32efb049c5', NULL, 1.5, 1),
        ('f3', 'Licence Droit', 'licence-droit', '978620ba-d64e-4830-8e49-cc7dc2cd716e', NULL, 3.0, 1)
    """)
    
    cursor.execute("""
        INSERT INTO proa_domains VALUES 
        ('ds1', 'data_science', 'informatique'),
        ('ml1', 'machine_learning', 'informatique'),
        ('fin1', 'finance', 'business'),
        ('law1', 'droit_prive', 'droit')
    """)
    
    cursor.execute("""
        INSERT INTO matcheur_proa_domains VALUES 
        ('f1', 'ds1', 1.0),
        ('f1', 'ml1', 1.0),
        ('f2', 'fin1', 1.0),
        ('f3', 'law1', 1.0)
    """)
    
    conn.commit()
    
    # Tester le moteur
    engine = FiliereEngineScore(conn)
    user_domains = ["data_science", "machine_learning", "python"]
    
    # Calculer les scores
    scores = engine.compute_filiere_scores(user_domains)
    
    print("\n" + "="*60)
    print("RÉSULTATS DU TEST")
    print("="*60)
    for score in scores:
        print(f"\n📚 {score.filiere_name}")
        print(f"   Cluster: {score.cluster}")
        print(f"   Score: {score.score:.2%}")
        print(f"   Compatibilité: {score.compatibility_level}")
        print(f"   Durée: {score.duration_years} ans")
        print(f"   Domaines matchés: {score.top_domains}")
    
    # Tester la sauvegarde
    print("\n" + "="*60)
    print("TEST DE SAUVEGARDE")
    print("="*60)
    engine.save_all_scores("user_test_123", scores, user_domains, "session_abc")
    
    # Tester la récupération
    saved_scores = engine.get_user_scores("user_test_123", limit=10)
    print(f"\n✅ {len(saved_scores)} scores récupérés depuis la base")
    for s in saved_scores[:3]:
        print(f"   - {s['filiere_name']}: {s['score']:.2%} ({s['compatibility_level']})")
    
    conn.close()
    
    return scores


if __name__ == "__main__":
    # Exécuter le test
    test_filiere_scoring()
# scripts/populate_quiz_test.py

from dotenv import load_dotenv
import os
load_dotenv()  # Charge les variables d'environnement du fichier .env

from storage.supabase import SupabaseStorage
import uuid
from datetime import datetime, timezone

storage = SupabaseStorage()

# -----------------------------
# 1️⃣ Créer un quiz test (ou récupérer l'existant)
# -----------------------------
quiz_code = "orientation_etudiant_v1"
existing_quiz = storage.fetch_one("orientation_quizzes", {"quiz_code": quiz_code})

if existing_quiz:
    quiz_id = existing_quiz["id"]
    print(f"Quiz déjà existant : {quiz_id}")
else:
    quiz = {
        "quiz_code": quiz_code,
        "target_profile": "etudiant",
        "version": 1,
        "title": "Quiz Orientation Étudiant v1",
        "description": "Quiz test pour l'engine rule/ml",
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    quiz_record = storage.insert("orientation_quizzes", quiz)
    quiz_id = quiz_record.get("id")
    print(f"Quiz créé : {quiz_id}")

# -----------------------------
# 2️⃣ Créer des questions si elles n'existent pas
# -----------------------------
questions = [
    {"question_code": "logic_1", "question_text": "Je résous facilement des problèmes logiques", "question_type": "likert", "order_index": 1, "is_required": True},
    {"question_code": "creativity_1", "question_text": "J'ai des idées créatives régulièrement", "question_type": "likert", "order_index": 2, "is_required": True},
    {"question_code": "entrepreneurship_1", "question_text": "Je prends des initiatives pour créer des projets", "question_type": "likert", "order_index": 3, "is_required": True},
]

question_ids = []
for q in questions:
    existing_q = storage.fetch_one("orientation_quiz_questions", {"quiz_id": quiz_id, "question_code": q["question_code"]})
    if existing_q:
        question_ids.append(existing_q["id"])
        print(f"Question déjà existante : {existing_q['question_code']} -> {existing_q['id']}")
    else:
        q["quiz_id"] = quiz_id
        q["created_at"] = datetime.now(timezone.utc).isoformat()
        rec = storage.insert("orientation_quiz_questions", q)
        question_ids.append(rec.get("id"))
        print(f"Question créée : {rec.get('question_code')} -> {rec.get('id')}")

# -----------------------------
# 3️⃣ Ajouter les poids des features
# -----------------------------
feature_map = {
    "logic_1": {"logic_score": 0.5},
    "creativity_1": {"creativity_score": 0.6},
    "entrepreneurship_1": {"entrepreneurship_score": 0.4},
}

for q_id, q in zip(question_ids, questions):
    question_code = q["question_code"]
    for feature_name, weight in feature_map.get(question_code, {}).items():
        # Vérifie si le poids existe déjà
        existing_weight = storage.fetch_one(
            "orientation_question_feature_weights",
            {"question_id": q_id, "feature_name": feature_name}
        )
        if existing_weight:
            print(f"Poids déjà existant : {question_code} -> {feature_name}={weight}")
        else:
            storage.insert("orientation_question_feature_weights", {
                "question_id": q_id,
                "feature_name": feature_name,
                "weight": weight
            })
            print(f"Poids ajouté : {question_code} -> {feature_name}={weight}")

# -----------------------------
# 4️⃣ Ajouter une réponse utilisateur simulée
# -----------------------------
user_id = str(uuid.uuid4())
answers = {
    "logic_1": 4,
    "creativity_1": 3,
    "entrepreneurship_1": 5,
}

response = {
    "user_id": user_id,
    "quiz_id": quiz_id,
    "answers": answers,
    "created_at": datetime.now(timezone.utc).isoformat()
}

resp_record = storage.insert("orientation_quiz_responses", response)
print(f"Réponse utilisateur créée : {resp_record.get('id')}")

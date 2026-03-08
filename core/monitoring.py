# core/monitoring.py

import logging
from typing import Dict, List
from datetime import datetime, timedelta
import statistics

from db.repository import (
    get_feedback_statistics,
    get_profiles_by_confidence,
    get_orientation_history,
)

logger = logging.getLogger("orientation.monitoring")


class MonitoringAlert:
    """Alerte de monitoring"""
    
    def __init__(self, level: str, message: str, data: Dict = None):
        self.level = level  # "info", "warning", "error"
        self.message = message
        self.data = data or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self):
        return {
            "level": self.level,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class HealthMonitor:
    """Monitore la santé globale du système PROA"""
    
    def __init__(self):
        self.alerts: List[MonitoringAlert] = []
    
    def check_all(self) -> Dict:
        """Lance tous les checks"""
        self.alerts = []
        
        self._check_feedback_metrics()
        self._check_low_confidence_profiles()
        
        return {
            "status": "healthy" if not self._has_critical_alerts() else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "alerts": [a.to_dict() for a in self.alerts],
        }
    
    def _check_feedback_metrics(self):
        """Vérifie les métriques de feedback"""
        try:
            stats = get_feedback_statistics(days=7)
            
            if stats["count"] == 0:
                self.alerts.append(MonitoringAlert(
                    "warning",
                    "Pas de feedback utilisateur cette semaine",
                    stats
                ))
                return
            
            # Satisfaction moyenne
            if stats["avg_satisfaction"] < 3.0:
                self.alerts.append(MonitoringAlert(
                    "warning",
                    f"Satisfaction moyenne basse: {stats['avg_satisfaction']:.2f}/5",
                    stats
                ))
            
            # Taux de succès
            if stats["success_rate"] < 0.7:
                self.alerts.append(MonitoringAlert(
                    "warning",
                    f"Taux de succès faible: {stats['success_rate']:.1%}",
                    stats
                ))
            
            # Taux de changement
            if stats["changed_rate"] > 0.5:
                self.alerts.append(MonitoringAlert(
                    "info",
                    f"Taux de changement orientation élevé: {stats['changed_rate']:.1%}",
                    stats
                ))
            
            logger.info(f"Feedback check OK | {stats}")
            
        except Exception as e:
            self.alerts.append(MonitoringAlert(
                "error",
                f"Erreur check feedback: {str(e)}"
            ))
    
    def _check_low_confidence_profiles(self):
        """Vérifie les profils avec basse confiance"""
        try:
            low_conf = get_profiles_by_confidence(min_confidence=0.3, limit=50)
            
            if len(low_conf) > 20:
                self.alerts.append(MonitoringAlert(
                    "warning",
                    f"{len(low_conf)} profils avec confiance < 30%",
                    {"count": len(low_conf)}
                ))
            
            if low_conf:
                confidences = [p["confidence"] for p in low_conf]
                avg_conf = statistics.mean(confidences)
                logger.info(f"Low confidence profiles: count={len(low_conf)}, avg={avg_conf:.2f}")
            
        except Exception as e:
            self.alerts.append(MonitoringAlert(
                "error",
                f"Erreur check confiance: {str(e)}"
            ))
    
    def _has_critical_alerts(self) -> bool:
        """Détecte les alertes critiques"""
        return any(a.level == "error" for a in self.alerts)


class VectorStatistics:
    """Analyse les statistiques des vecteurs d'orientation"""
    
    @staticmethod
    def analyze_user_profiles(user_id: str, limit: int = 20) -> Dict:
        """Analyse la progression des profils d'un utilisateur"""
        try:
            history = get_orientation_history(user_id, limit=limit)
            
            if not history:
                return {"count": 0, "message": "Pas de profils"}
            
            # Extraire les confidences
            confidences = [p["confidence"] for p in history]
            
            # Trend
            trend = "stable"
            if len(confidences) >= 2:
                recent_avg = statistics.mean(confidences[-3:]) if len(confidences) >= 3 else confidences[-1]
                older_avg = statistics.mean(confidences[:3]) if len(confidences) >= 3 else confidences[0]
                
                if recent_avg > older_avg + 0.1:
                    trend = "improving"
                elif recent_avg < older_avg - 0.1:
                    trend = "degrading"
            
            return {
                "count": len(history),
                "avg_confidence": round(statistics.mean(confidences), 4),
                "min_confidence": round(min(confidences), 4),
                "max_confidence": round(max(confidences), 4),
                "trend": trend,
                "last_profile": history[0] if history else None,
            }
        
        except Exception as e:
            logger.exception(f"Erreur analyse profiles utilisateur: {str(e)}")
            return {"error": str(e)}


# Singleton monitor
_monitor = HealthMonitor()


def get_health_status() -> Dict:
    """Retourne l'état de santé du système"""
    return _monitor.check_all()


def analyze_user_progression(user_id: str) -> Dict:
    """Analyse la progression d'un utilisateur"""
    return VectorStatistics.analyze_user_profiles(user_id)

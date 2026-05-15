"""
Monitoring - Surveillance et métriques du système PROA
Version 2.0 - Support du scoring V2, alerting avancé, métriques temps réel
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import statistics
import threading

from db.repository import (
    get_feedback_statistics,
    get_profiles_by_confidence,
    get_orientation_history,
)

logger = logging.getLogger("orientation.monitoring")


# ============================================================================
# MODÈLES DE DONNÉES
# ============================================================================

@dataclass
class MonitoringAlert:
    """Alerte de monitoring enrichie"""
    level: str  # "info", "warning", "error", "critical"
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PerformanceMetric:
    """Métrique de performance"""
    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ScoringMetrics:
    """Métriques spécifiques au scoring V2"""
    method: str  # "rule", "ml", "v2", "hybrid"
    confidence: float
    computation_time_ms: float
    domains_count: int
    skills_count: int
    feature_coverage: float
    has_bac: bool
    dominant_cluster: Optional[str] = None


# ============================================================================
# HEALTH MONITOR AMÉLIORÉ
# ============================================================================

class HealthMonitor:
    """
    Monitore la santé globale du système PROA V2.
    
    Améliorations:
    - Métriques de performance temps réel
    - Alerting sur seuils configurables
    - Historique des métriques
    - Monitoring du scoring V2
    """
    
    def __init__(self, alert_thresholds: Optional[Dict] = None):
        """
        Initialise le moniteur.
        
        Args:
            alert_thresholds: Seuils personnalisés pour les alertes
        """
        self.alerts: List[MonitoringAlert] = []
        self.metrics_history: Dict[str, deque] = {}
        self.alert_thresholds = alert_thresholds or self._default_thresholds()
        
        # Thread pour monitoring continu (optionnel)
        self._monitoring_thread = None
        self._stop_monitoring = False
        
        logger.info("HealthMonitor V2 initialisé")
    
    def _default_thresholds(self) -> Dict[str, Any]:
        """Seuils par défaut pour les alertes."""
        return {
            "min_satisfaction": 3.0,  # /5
            "min_success_rate": 0.7,  # 70%
            "max_confidence_change": 0.1,  # +/-10%
            "min_avg_confidence": 0.6,  # 60%
            "max_low_confidence_profiles": 20,
            "max_response_time_ms": 500,  # 500ms
            "min_feedback_count": 5,  # par semaine
        }
    
    def check_all(self, metrics: Optional[List[PerformanceMetric]] = None) -> Dict[str, Any]:
        """
        Lance tous les checks de santé.
        
        Args:
            metrics: Métriques de performance optionnelles
        
        Returns:
            État de santé complet
        """
        self.alerts = []
        
        # 1. Métriques de feedback
        self._check_feedback_metrics()
        
        # 2. Confiance des profils
        self._check_low_confidence_profiles()
        
        # 3. Performance (si fournie)
        if metrics:
            self._check_performance_metrics(metrics)
        
        # 4. Scoring V2 specific
        self._check_scoring_v2_health()
        
        # 5. Détection d'anomalies
        self._detect_anomalies()
        
        # Déterminer le statut global
        status = self._determine_status()
        
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "alerts": [a.to_dict() for a in self.alerts],
            "summary": self._generate_summary(),
        }
    
    def _check_feedback_metrics(self):
        """Vérifie les métriques de feedback utilisateur."""
        try:
            stats = get_feedback_statistics(days=7)
            
            if stats["count"] == 0:
                self.alerts.append(MonitoringAlert(
                    level="warning",
                    message="Aucun feedback utilisateur cette semaine",
                    data=stats,
                    source="feedback"
                ))
                return
            
            # Satisfaction moyenne
            if stats["avg_satisfaction"] < self.alert_thresholds["min_satisfaction"]:
                self.alerts.append(MonitoringAlert(
                    level="warning",
                    message=f"Satisfaction moyenne basse: {stats['avg_satisfaction']:.2f}/5",
                    data=stats,
                    source="feedback"
                ))
            
            # Taux de succès
            if stats["success_rate"] < self.alert_thresholds["min_success_rate"]:
                self.alerts.append(MonitoringAlert(
                    level="warning",
                    message=f"Taux de succès faible: {stats['success_rate']:.1%}",
                    data=stats,
                    source="feedback"
                ))
            
            # Taux de changement orientation
            if stats.get("changed_rate", 0) > 0.5:
                self.alerts.append(MonitoringAlert(
                    level="info",
                    message=f"Taux de changement orientation élevé: {stats['changed_rate']:.1%}",
                    data=stats,
                    source="feedback"
                ))
            
            logger.info(f"Feedback check OK | count={stats['count']}, satisfaction={stats.get('avg_satisfaction', 0):.2f}")
            
        except Exception as e:
            self.alerts.append(MonitoringAlert(
                level="error",
                message=f"Erreur check feedback: {str(e)}",
                source="feedback"
            ))
    
    def _check_low_confidence_profiles(self):
        """Vérifie les profils avec faible confiance."""
        try:
            low_conf = get_profiles_by_confidence(min_confidence=0.3, limit=50)
            count = len(low_conf)
            
            if count > self.alert_thresholds["max_low_confidence_profiles"]:
                self.alerts.append(MonitoringAlert(
                    level="warning",
                    message=f"{count} profils avec confiance < 30%",
                    data={"count": count, "threshold": self.alert_thresholds["max_low_confidence_profiles"]},
                    source="confidence"
                ))
            
            if low_conf:
                confidences = [p["confidence"] for p in low_conf]
                avg_conf = statistics.mean(confidences)
                logger.info(f"Low confidence profiles: count={count}, avg={avg_conf:.2f}")
            
        except Exception as e:
            self.alerts.append(MonitoringAlert(
                level="error",
                message=f"Erreur check confiance: {str(e)}",
                source="confidence"
            ))
    
    def _check_performance_metrics(self, metrics: List[PerformanceMetric]):
        """Vérifie les métriques de performance."""
        for metric in metrics:
            if metric.name == "avg_response_time_ms":
                if metric.value > self.alert_thresholds["max_response_time_ms"]:
                    self.alerts.append(MonitoringAlert(
                        level="warning",
                        message=f"Temps de réponse élevé: {metric.value:.0f}ms",
                        data={"value": metric.value, "threshold": self.alert_thresholds["max_response_time_ms"]},
                        source="performance"
                    ))
            
            # Stocker l'historique
            if metric.name not in self.metrics_history:
                self.metrics_history[metric.name] = deque(maxlen=100)
            self.metrics_history[metric.name].append(metric)
    
    def _check_scoring_v2_health(self):
        """Vérifie la santé du scoring V2."""
        try:
            # Récupérer les statistiques des profils récents
            recent_profiles = get_orientation_history(limit=100)
            
            if recent_profiles:
                # Distribution des méthodes de scoring
                methods = [p.get("scoring_method", "unknown") for p in recent_profiles]
                method_counts = {}
                for method in methods:
                    method_counts[method] = method_counts.get(method, 0) + 1
                
                # Confiance moyenne par méthode
                confidence_by_method = {}
                for profile in recent_profiles:
                    method = profile.get("scoring_method", "unknown")
                    confidence = profile.get("confidence", 0)
                    if method not in confidence_by_method:
                        confidence_by_method[method] = []
                    confidence_by_method[method].append(confidence)
                
                avg_confidence = {
                    method: statistics.mean(confs) 
                    for method, confs in confidence_by_method.items()
                }
                
                # Alerte si confiance V2 trop basse
                if "v2" in avg_confidence and avg_confidence["v2"] < self.alert_thresholds["min_avg_confidence"]:
                    self.alerts.append(MonitoringAlert(
                        level="warning",
                        message=f"Confiance scoring V2 faible: {avg_confidence['v2']:.2%}",
                        data={"avg_confidence": avg_confidence["v2"], "method": "v2"},
                        source="scoring_v2"
                    ))
                
                logger.info(f"Scoring V2 health: methods={method_counts}, confidences={avg_confidence}")
            
        except Exception as e:
            logger.warning(f"Could not check scoring V2 health: {e}")
    
    def _detect_anomalies(self):
        """Détecte des anomalies dans les métriques."""
        for metric_name, history in self.metrics_history.items():
            if len(history) < 10:
                continue
            
            values = [m.value for m in history]
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0
            
            last_value = values[-1]
            
            # Détection de pics (3 écarts-type)
            if std > 0 and abs(last_value - mean) > 3 * std:
                self.alerts.append(MonitoringAlert(
                    level="warning",
                    message=f"Anomalie détectée sur {metric_name}",
                    data={
                        "metric": metric_name,
                        "current": last_value,
                        "mean": round(mean, 4),
                        "std": round(std, 4),
                        "z_score": round(abs(last_value - mean) / std, 2)
                    },
                    source="anomaly"
                ))
    
    def _determine_status(self) -> str:
        """Détermine le statut global basé sur les alertes."""
        if any(a.level == "critical" for a in self.alerts):
            return "critical"
        if any(a.level == "error" for a in self.alerts):
            return "degraded"
        if any(a.level == "warning" for a in self.alerts):
            return "warning"
        return "healthy"
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Génère un résumé des métriques."""
        summary = {
            "total_alerts": len(self.alerts),
            "by_level": {"info": 0, "warning": 0, "error": 0, "critical": 0},
            "by_source": {}
        }
        
        for alert in self.alerts:
            summary["by_level"][alert.level] = summary["by_level"].get(alert.level, 0) + 1
            summary["by_source"][alert.source] = summary["by_source"].get(alert.source, 0) + 1
        
        return summary
    
    def start_continuous_monitoring(self, interval_seconds: int = 60):
        """Démarre le monitoring continu dans un thread séparé."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Monitoring déjà actif")
            return
        
        self._stop_monitoring = False
        
        def monitor_loop():
            while not self._stop_monitoring:
                try:
                    self.check_all()
                    time.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Monitoring loop error: {e}")
        
        self._monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitoring_thread.start()
        logger.info(f"Continuous monitoring started (interval={interval_seconds}s)")
    
    def stop_continuous_monitoring(self):
        """Arrête le monitoring continu."""
        self._stop_monitoring = True
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Continuous monitoring stopped")
    
    def record_metric(self, name: str, value: float, unit: str = "ms"):
        """Enregistre une métrique de performance."""
        metric = PerformanceMetric(name=name, value=value, unit=unit)
        if name not in self.metrics_history:
            self.metrics_history[name] = deque(maxlen=100)
        self.metrics_history[name].append(metric)


# ============================================================================
# ANALYSE STATISTIQUE AVANCÉE
# ============================================================================

class VectorStatistics:
    """Analyse les statistiques des vecteurs d'orientation V2."""
    
    @staticmethod
    def analyze_user_profiles(user_id: str, limit: int = 20) -> Dict[str, Any]:
        """
        Analyse la progression des profils d'un utilisateur.
        
        Returns:
            Statistiques détaillées avec tendances
        """
        try:
            history = get_orientation_history(user_id, limit=limit)
            
            if not history:
                return {"count": 0, "message": "Pas de profils"}
            
            # Extraire les métriques
            confidences = [p.get("confidence", 0) for p in history]
            timestamps = [p.get("timestamp") for p in history]
            
            # Analyse de tendance
            trend = "stable"
            trend_strength = 0.0
            
            if len(confidences) >= 2:
                recent_avg = statistics.mean(confidences[-3:]) if len(confidences) >= 3 else confidences[-1]
                older_avg = statistics.mean(confidences[:3]) if len(confidences) >= 3 else confidences[0]
                trend_strength = recent_avg - older_avg
                
                if trend_strength > 0.1:
                    trend = "improving"
                elif trend_strength < -0.1:
                    trend = "degrading"
            
            # Variabilité
            variance = statistics.variance(confidences) if len(confidences) > 1 else 0
            
            return {
                "count": len(history),
                "avg_confidence": round(statistics.mean(confidences), 4),
                "min_confidence": round(min(confidences), 4),
                "max_confidence": round(max(confidences), 4),
                "variance": round(variance, 4),
                "trend": trend,
                "trend_strength": round(trend_strength, 4),
                "last_profile": history[0] if history else None,
                "first_profile": history[-1] if history else None,
            }
        
        except Exception as e:
            logger.exception(f"Erreur analyse profiles utilisateur: {str(e)}")
            return {"error": str(e)}
    
    @staticmethod
    def aggregate_scoring_metrics(metrics_list: List[ScoringMetrics]) -> Dict[str, Any]:
        """
        Agrège les métriques de scoring pour analyse globale.
        """
        if not metrics_list:
            return {"count": 0}
        
        # Par méthode
        by_method = {}
        for metric in metrics_list:
            if metric.method not in by_method:
                by_method[metric.method] = []
            by_method[metric.method].append(metric)
        
        # Statistiques par méthode
        method_stats = {}
        for method, metrics in by_method.items():
            confidences = [m.confidence for m in metrics]
            times = [m.computation_time_ms for m in metrics]
            
            method_stats[method] = {
                "count": len(metrics),
                "avg_confidence": round(statistics.mean(confidences), 4),
                "avg_time_ms": round(statistics.mean(times), 2),
                "p95_time_ms": round(sorted(times)[int(len(times) * 0.95)], 2) if times else 0,
                "bac_usage": sum(1 for m in metrics if m.has_bac) / len(metrics),
            }
        
        # Distribution des clusters dominants
        clusters = [m.dominant_cluster for m in metrics_list if m.dominant_cluster]
        cluster_distribution = {}
        for cluster in clusters:
            cluster_distribution[cluster] = cluster_distribution.get(cluster, 0) + 1
        
        return {
            "total": len(metrics_list),
            "by_method": method_stats,
            "cluster_distribution": cluster_distribution,
            "avg_feature_coverage": round(statistics.mean([m.feature_coverage for m in metrics_list]), 4),
        }


# ============================================================================
# MONITEUR DE PERFORMANCE EN TEMPS RÉEL
# ============================================================================

class PerformanceMonitor:
    """Moniteur de performance pour le scoring V2."""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}
        self.start_times: Dict[str, float] = {}
    
    def start_operation(self, operation_name: str):
        """Démarre le chronométrage d'une opération."""
        self.start_times[operation_name] = time.time()
    
    def end_operation(self, operation_name: str) -> float:
        """Termine le chronométrage et retourne la durée en ms."""
        if operation_name not in self.start_times:
            return 0.0
        
        duration_ms = (time.time() - self.start_times[operation_name]) * 1000
        
        if operation_name not in self.metrics:
            self.metrics[operation_name] = []
        self.metrics[operation_name].append(duration_ms)
        
        # Garder seulement les 100 dernières métriques
        if len(self.metrics[operation_name]) > 100:
            self.metrics[operation_name] = self.metrics[operation_name][-100:]
        
        return duration_ms
    
    def get_stats(self, operation_name: str) -> Dict[str, float]:
        """Retourne les statistiques pour une opération."""
        if operation_name not in self.metrics or not self.metrics[operation_name]:
            return {"count": 0}
        
        values = self.metrics[operation_name]
        return {
            "count": len(values),
            "avg_ms": round(statistics.mean(values), 2),
            "min_ms": round(min(values), 2),
            "max_ms": round(max(values), 2),
            "p95_ms": round(sorted(values)[int(len(values) * 0.95)], 2),
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Retourne les statistiques pour toutes les opérations."""
        return {op: self.get_stats(op) for op in self.metrics}
    
    def reset(self):
        """Réinitialise toutes les métriques."""
        self.metrics.clear()
        self.start_times.clear()


# ============================================================================
# SINGLETONS ET FONCTIONS DE CONVENANCE
# ============================================================================

_health_monitor = HealthMonitor()
_performance_monitor = PerformanceMonitor()


def get_health_status() -> Dict[str, Any]:
    """Retourne l'état de santé du système."""
    return _health_monitor.check_all()


def get_health_monitor() -> HealthMonitor:
    """Retourne l'instance globale du health monitor."""
    return _health_monitor


def get_performance_monitor() -> PerformanceMonitor:
    """Retourne l'instance globale du performance monitor."""
    return _performance_monitor


def analyze_user_progression(user_id: str) -> Dict[str, Any]:
    """Analyse la progression d'un utilisateur."""
    return VectorStatistics.analyze_user_profiles(user_id)


def record_scoring_metric(metric: ScoringMetrics):
    """Enregistre une métrique de scoring."""
    # À implémenter: stockage en base pour analyse
    logger.debug(f"Scoring metric: {metric.method} | confidence={metric.confidence:.2%} | time={metric.computation_time_ms:.0f}ms")


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test du monitoring
    monitor = HealthMonitor()
    
    # Simuler des métriques
    test_metrics = [
        PerformanceMetric(name="avg_response_time_ms", value=450, unit="ms"),
        PerformanceMetric(name="requests_per_second", value=12.5, unit="req/s"),
    ]
    
    result = monitor.check_all(metrics=test_metrics)
    
    print("\n📊 Health Check Results")
    print("=" * 50)
    print(f"Status: {result['status']}")
    print(f"Total alerts: {result['summary']['total_alerts']}")
    
    for alert in result['alerts']:
        print(f"  [{alert['level']}] {alert['message']} ({alert['source']})")
    
    # Test performance monitor
    perf = PerformanceMonitor()
    perf.start_operation("test_op")
    time.sleep(0.05)
    duration = perf.end_operation("test_op")
    
    print(f"\n⚡ Performance: {duration:.2f}ms")
    print(f"Stats: {perf.get_stats('test_op')}")
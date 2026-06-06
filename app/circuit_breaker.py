"""
app/circuit_breaker.py — Circuit Breaker pour appels n8n

3 états :
  CLOSED    → n8n fonctionne normalement
  OPEN      → n8n down → FastAPI orchestre lui-même
  HALF_OPEN → test après recovery_time secondes

Règles :
  3 erreurs consécutives → OPEN
  Après 30s → HALF_OPEN (on reteste)
  Succès → CLOSED
"""

import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,       # nb erreurs avant OPEN
        recovery_time: int = 30,  # secondes avant HALF_OPEN
        timeout: float = 5.0,     # timeout appel n8n
    ):
        self.state          = "CLOSED"
        self.failure_count  = 0
        self.last_failure   : Optional[datetime] = None
        self.threshold      = threshold
        self.recovery_time  = recovery_time
        self.timeout        = timeout

    def _check_recovery(self):
        """OPEN → HALF_OPEN si recovery_time écoulé."""
        if self.state == "OPEN" and self.last_failure:
            elapsed = (datetime.now() - self.last_failure).total_seconds()
            if elapsed >= self.recovery_time:
                self.state = "HALF_OPEN"
                logger.info("[CircuitBreaker] OPEN → HALF_OPEN (test de récupération)")

    def _on_success(self):
        """Succès → CLOSED."""
        if self.state != "CLOSED":
            logger.info(f"[CircuitBreaker] {self.state} → CLOSED")
        self.state         = "CLOSED"
        self.failure_count = 0
        self.last_failure  = None

    def _on_failure(self):
        """Erreur → incrémente compteur → OPEN si threshold atteint."""
        self.failure_count += 1
        self.last_failure   = datetime.now()
        if self.failure_count >= self.threshold:
            if self.state != "OPEN":
                logger.warning(
                    f"[CircuitBreaker] CLOSED → OPEN "
                    f"({self.failure_count} erreurs consécutives)"
                )
            self.state = "OPEN"

    def call(self, url: str, payload: dict) -> Optional[dict]:
        """
        Appelle n8n via webhook.
        Retourne la réponse si succès, None si n8n indisponible.
        Le caller doit gérer le fallback FastAPI si None est retourné.
        """
        self._check_recovery()

        # OPEN → pas d'appel, fallback direct
        if self.state == "OPEN":
            logger.warning(f"[CircuitBreaker] OPEN — appel n8n bloqué : {url}")
            return None

        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            self._on_success()
            logger.info(f"[CircuitBreaker] ✅ n8n appelé avec succès : {url}")
            return response.json() if response.content else {}

        except httpx.TimeoutException:
            logger.warning(f"[CircuitBreaker] ⏱️ Timeout n8n : {url}")
            self._on_failure()
            return None

        except httpx.HTTPStatusError as e:
            logger.warning(f"[CircuitBreaker] ❌ HTTP {e.response.status_code} n8n : {url}")
            self._on_failure()
            return None

        except Exception as e:
            logger.warning(f"[CircuitBreaker] ❌ Erreur n8n : {url} — {e}")
            self._on_failure()
            return None

    @property
    def is_available(self) -> bool:
        """True si n8n est disponible (CLOSED ou HALF_OPEN)."""
        self._check_recovery()
        return self.state != "OPEN"

    def status(self) -> dict:
        """Retourne l'état actuel du circuit breaker."""
        return {
            "state"        : self.state,
            "failure_count": self.failure_count,
            "last_failure" : str(self.last_failure) if self.last_failure else None,
            "available"    : self.is_available,
        }


# ── Instance globale — partagée dans tout le backend ─────────────────────────
n8n_breaker = CircuitBreaker(threshold=3, recovery_time=30, timeout=5.0)
"""Garde-fou financier : on s'arrête avant de dépasser le plafond, jamais après."""
import threading


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, cap_usd):
        self.cap = float(cap_usd)
        self.spent = 0.0
        self.by_system = {}
        self._lock = threading.Lock()

    def check(self, reserve=0.0):
        with self._lock:
            if self.spent + reserve > self.cap:
                raise BudgetExceeded(f"plafond {self.cap:.2f} $ atteint (dépensé {self.spent:.4f} $)")

    def add(self, system, cost):
        with self._lock:
            self.spent += cost or 0.0
            self.by_system[system] = self.by_system.get(system, 0.0) + (cost or 0.0)


def tokens_estimate(text):
    """Estimation grossière (≈ 3,6 caractères par token) ; sert uniquement à prévoir le coût, jamais à le mesurer."""
    return max(1, int(len(text) / 3.6))

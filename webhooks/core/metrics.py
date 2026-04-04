from collections import Counter
from typing import Counter as CounterType

metrics: CounterType[str] = Counter()


def inc(name):
    metrics[name] += 1


def snapshot():
    """Retorna una copia de los contadores actuales."""
    return dict(metrics)


def export_prometheus_text(prefix="webhooks"):
    """
    Exporta métricas en formato texto compatible con Prometheus.

    Notas:
    - Este exportador usa los contadores in-memory del proceso actual.
    - En despliegues con múltiples procesos/instancias, cada uno expone su propia vista.
    """
    lines = []

    for raw_name, value in sorted(metrics.items()):
        metric_name = f"{prefix}_{raw_name.replace('.', '_')}"
        lines.append(f"# TYPE {metric_name} counter")
        lines.append(f"{metric_name} {value}")

    return "\n".join(lines) + "\n"

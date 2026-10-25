"""Contratos futuros. Nenhum cliente pago é instanciado pelo pipeline."""
from typing import Iterable, Protocol


class AdSource(Protocol):
    requests: int

    def ads(self) -> Iterable[tuple[dict, str]]: ...


class AIClassifier(Protocol):
    def classify(self, evidence: dict) -> dict:
        """Implementação futura exige autorização explícita e orçamento."""
        ...

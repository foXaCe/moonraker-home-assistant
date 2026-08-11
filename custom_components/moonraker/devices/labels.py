"""Libellés français pour les entités dynamiques (objets Klipper)."""

SUFFIXES_FR = {
    "temperature": "Température",
    "temp": "Température",
    "power": "Puissance",
    "target": "Cible",
    "speed": "Vitesse",
    "pressure": "Pression",
    "humidity": "Humidité",
    "gas": "Gaz",
    "load": "Charge",
    "awake": "Temps d'éveil",
    "diameter": "Diamètre",
    "raw": "Brut",
    "active": "Actif",
    "rpm": "RPM",
}


def fr_name(suffix_key: str, object_name: str) -> str:
    """Nom français d'une entité dynamique, ex. 'Température du plateau'."""
    suffix = SUFFIXES_FR.get(suffix_key, suffix_key)
    obj = object_name.strip()
    if obj.casefold() in ("bed",):
        return f"{suffix} du plateau"
    if obj.casefold() in ("extruder",):
        return f"{suffix} de l'extrudeuse"
    if obj.casefold() in ("extruder1",):
        return f"{suffix} de l'extrudeuse 1"
    if obj.casefold() in ("chamber",):
        return f"{suffix} de l'enceinte"
    return f"{suffix} {obj}"

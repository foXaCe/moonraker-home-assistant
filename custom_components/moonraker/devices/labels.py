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


# Préfixes de type d'objet Klipper. Seul le type est traduit : le nom qui suit
# vient du printer.cfg de l'utilisateur et doit rester tel quel.
PREFIXES_FR = {
    "output_pin": "Sortie",
    "smart_output_pin": "Sortie intelligente",
}


def fr_object_label(obj: str) -> str:
    """Nom français d'un objet Klipper « <type> <nom> »."""
    parts = obj.split(maxsplit=1)
    prefix = PREFIXES_FR.get(parts[0])
    if prefix is None:
        return obj.replace("_", " ").title()
    if len(parts) == 1:
        return prefix
    return f"{prefix} {parts[1].replace('_', ' ').title()}"

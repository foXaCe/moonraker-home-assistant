"""Libellés localisés pour les entités dynamiques (objets Klipper).

Les noms codés en dur ici ne concernent que le *libellé* des entités dont le
type est déduit de la configuration de l'utilisateur (capteurs de température,
ventilateurs, MCU…). Le nom de l'objet Klipper lui-même n'est jamais traduit :
il vient du `printer.cfg`.
"""

from __future__ import annotations

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

SUFFIXES_EN = {
    "temperature": "Temperature",
    "temp": "Temperature",
    "power": "Power",
    "target": "Target",
    "speed": "Speed",
    "pressure": "Pressure",
    "humidity": "Humidity",
    "gas": "Gas",
    "load": "Load",
    "awake": "Awake Time",
    "diameter": "Diameter",
    "raw": "Raw",
    "active": "Active",
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


def en_name(suffix_key: str, object_name: str) -> str:
    """Nom anglais d'une entité dynamique, ex. 'Bed temperature'."""
    suffix = SUFFIXES_EN.get(suffix_key, suffix_key)
    return f"{object_name.strip().title()} {suffix}".strip()


# Préfixes de type d'objet Klipper. Seul le type est traduit : le nom qui suit
# vient du printer.cfg de l'utilisateur et doit rester tel quel.
PREFIXES_FR = {
    "output_pin": "Sortie",
    "smart_output_pin": "Sortie intelligente",
}

PREFIXES_EN = {
    "output_pin": "Output",
    "smart_output_pin": "Smart Output",
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


def en_object_label(obj: str) -> str:
    """Nom anglais d'un objet Klipper « <type> <nom> »."""
    parts = obj.split(maxsplit=1)
    prefix = PREFIXES_EN.get(parts[0])
    if prefix is None:
        return obj.replace("_", " ").title()
    if len(parts) == 1:
        return prefix
    return f"{prefix} {parts[1].replace('_', ' ').title()}"


def _base_language(language: str | None) -> str:
    """Réduit une locale HA (ex. 'fr-FR') à sa langue de base."""
    if not language:
        return "en"
    return language.replace("_", "-").split("-")[0].lower()


def _is_french(language: str | None) -> bool:
    return _base_language(language) == "fr"


def _pick(language: str | None, french: str, english: str) -> str:
    """Choisit le libellé selon la langue configurée dans Home Assistant."""
    if _is_french(language):
        return french
    return english


def localized_name(language: str | None, suffix_key: str, object_name: str) -> str:
    """Libellé localisé d'une entité dynamique."""
    return _pick(
        language,
        fr_name(suffix_key, object_name),
        en_name(suffix_key, object_name),
    )


def localized_object_label(language: str | None, obj: str) -> str:
    """Libellé localisé d'un objet Klipper « <type> <nom> »."""
    return _pick(language, fr_object_label(obj), en_object_label(obj))


# Actions des boutons de service Moonraker (macro.py).
SERVICE_ACTIONS = {
    "start": ("Démarrer", "Start"),
    "stop": ("Arrêter", "Stop"),
    "restart": ("Redémarrer", "Restart"),
}


def localized_service_name(language: str | None, action: str, service: str) -> str:
    """Libellé localisé d'un bouton de service, ex. 'Arrêter klipper'."""
    french, english = SERVICE_ACTIONS[action]
    return f"{_pick(language, french, english)} {service}"


def localized_fan(language: str | None) -> str:
    """Nom localisé du ventilateur de refroidissement principal."""
    return _pick(language, "Ventilateur", "Fan")


def localized_filament_width_sensor(language: str | None) -> str:
    """Nom localisé par défaut d'un capteur de largeur de filament."""
    return _pick(language, "Capteur de largeur de filament", "Filament Width Sensor")


def localized_update_name(language: str | None, component: str) -> str:
    """Libellé localisé d'une entité de mise à jour."""
    title = component.title()
    return _pick(language, f"Mise à jour {title}", f"Update {title}")


def localized_pending_packages(language: str | None, count: int) -> str:
    """Message localisé du nombre de paquets système à mettre à jour."""
    return _pick(
        language,
        f"{count} paquet(s) à mettre à jour",
        f"{count} package(s) to update",
    )

"""Test localised labels for dynamic Klipper entities."""

from custom_components.moonraker.devices.labels import (
    en_name,
    en_object_label,
    fr_name,
    fr_object_label,
    localized_fan,
    localized_filament_width_sensor,
    localized_name,
    localized_object_label,
    localized_pending_packages,
    localized_service_name,
    localized_update_name,
)


def test_fr_name_bed():
    """Bed objects map to 'du plateau'."""
    assert fr_name("temperature", "Bed") == "Température du plateau"


def test_fr_name_extruder():
    """Extruder objects map to 'de l'extrudeuse'."""
    assert fr_name("target", "extruder") == "Cible de l'extrudeuse"
    assert fr_name("target", "Extruder1") == "Cible de l'extrudeuse 1"


def test_fr_name_chamber():
    """Chamber objects map to 'de l'enceinte'."""
    assert fr_name("temperature", "Chamber") == "Température de l'enceinte"


def test_fr_name_generic():
    """Other objects keep their name appended to the suffix."""
    assert fr_name("rpm", "Controller Fan") == "RPM Controller Fan"


def test_fr_name_unknown_suffix():
    """Unknown suffixes are passed through unchanged."""
    assert fr_name("load", "mcu") == "Charge mcu"
    assert fr_name("custom", "Part") == "custom Part"


def test_fr_object_label_translates_known_prefix():
    """The Klipper object type is translated, the user-given name is not."""
    assert fr_object_label("output_pin caselight") == "Sortie Caselight"
    assert fr_object_label("smart_output_pin polar_cooler") == (
        "Sortie intelligente Polar Cooler"
    )


def test_fr_object_label_without_name():
    """A bare object type keeps just its translated prefix."""
    assert fr_object_label("output_pin") == "Sortie"


def test_fr_object_label_unknown_prefix_is_left_alone():
    """An object type with no translation keeps its titled form."""
    assert fr_object_label("neopixel my_led") == "Neopixel My Led"


def test_en_name_generic():
    """English names put the object before the translated suffix."""
    assert en_name("temperature", "Bed") == "Bed Temperature"
    assert en_name("speed", "heater fan") == "Heater Fan Speed"
    assert en_name("rpm", "Controller Fan") == "Controller Fan RPM"


def test_en_name_unknown_suffix():
    """Unknown English suffixes are passed through unchanged."""
    assert en_name("custom", "Part") == "Part custom"


def test_en_object_label_translates_known_prefix():
    """English output pin labels translate the Klipper object type."""
    assert en_object_label("output_pin caselight") == "Output Caselight"
    assert en_object_label("smart_output_pin polar_cooler") == (
        "Smart Output Polar Cooler"
    )


def test_en_object_label_without_name():
    """A bare English object type keeps just its translated prefix."""
    assert en_object_label("output_pin") == "Output"


def test_en_object_label_unknown_prefix_is_left_alone():
    """An English object type with no translation keeps its titled form."""
    assert en_object_label("neopixel my_led") == "Neopixel My Led"


def test_localized_name_follows_language():
    """The French label is used for French, the English one otherwise."""
    assert localized_name("fr", "temperature", "Bed") == "Température du plateau"
    assert localized_name("fr-FR", "temperature", "Bed") == "Température du plateau"
    assert localized_name("en", "temperature", "Bed") == "Bed Temperature"
    assert localized_name("en-US", "temperature", "Bed") == "Bed Temperature"
    assert localized_name(None, "temperature", "Bed") == "Bed Temperature"
    assert localized_name("de", "temperature", "Bed") == "Bed Temperature"


def test_localized_object_label_follows_language():
    """Pin labels follow the configured language."""
    assert localized_object_label("fr", "output_pin caselight") == "Sortie Caselight"
    assert localized_object_label("en", "output_pin caselight") == "Output Caselight"


def test_localized_service_name_follows_language():
    """Service button labels follow the configured language."""
    assert localized_service_name("fr", "stop", "klipper") == "Arrêter klipper"
    assert localized_service_name("fr", "start", "klipper") == "Démarrer klipper"
    assert localized_service_name("fr", "restart", "klipper") == "Redémarrer klipper"
    assert localized_service_name("en", "stop", "klipper") == "Stop klipper"
    assert localized_service_name("en", "start", "klipper") == "Start klipper"
    assert localized_service_name("en", "restart", "klipper") == "Restart klipper"


def test_localized_generic_names_follow_language():
    """Generic dynamic names follow the configured language."""
    assert localized_fan("fr") == "Ventilateur"
    assert localized_fan("en") == "Fan"
    assert localized_filament_width_sensor("fr") == "Capteur de largeur de filament"
    assert localized_filament_width_sensor("en") == "Filament Width Sensor"


def test_localized_update_labels_follow_language():
    """Update entity names and package counts follow the language."""
    assert localized_update_name("fr", "crownest") == "Mise à jour Crownest"
    assert localized_update_name("en", "crownest") == "Update Crownest"
    assert localized_pending_packages("fr", 3) == "3 paquet(s) à mettre à jour"
    assert localized_pending_packages("en", 3) == "3 package(s) to update"

"""Test French labels for dynamic Klipper entities."""

from custom_components.moonraker.devices.labels import fr_name


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

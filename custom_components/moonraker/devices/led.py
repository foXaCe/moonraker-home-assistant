"""LED device description builders for the Moonraker integration."""

from __future__ import annotations


from homeassistant.components.light.const import ColorMode

from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerLightSensorDescription


async def build_led_lights(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerLightSensorDescription]:
    """Build LED light descriptions from the printer object list."""

    object_list = coordinator.objects_list or {"objects": []}

    settings = coordinator.configfile_settings or {}

    lights: list[MoonrakerLightSensorDescription] = []
    for obj in object_list.get("objects", []):
        if (
            not obj.startswith("led ")
            and not obj.startswith("neopixel ")
            and not obj.startswith("dotstar ")
            and not obj.startswith("pca9533 ")
            and not obj.startswith("pca9632 ")
        ):
            continue

        led_type = obj.split()[0]
        color_mode = ColorMode.UNKNOWN
        conf = settings.get(obj.lower(), {})

        if led_type == "led":
            num_led_pins = 0
            for pin in ["red_pin", "green_pin", "blue_pin", "white_pin"]:
                if pin in conf:
                    num_led_pins += 1

            if num_led_pins == 0:
                continue
            elif num_led_pins == 1:
                color_mode = ColorMode.BRIGHTNESS
            elif num_led_pins == 4 or "white_pin" in conf:
                color_mode = ColorMode.RGBW
            elif "red_pin" in conf and "green_pin" in conf and "blue_pin" in conf:
                color_mode = ColorMode.RGB
        elif led_type == "neopixel" or led_type == "pca9632":
            if "color_order" in conf and "W" in conf["color_order"]:
                color_mode = ColorMode.RGBW
            else:
                color_mode = ColorMode.RGB
        elif led_type == "dotstar":
            color_mode = ColorMode.RGB
        elif led_type == "pca9533":
            color_mode = ColorMode.RGBW

        desc = MoonrakerLightSensorDescription(
            key=obj,
            sensor_name=obj,
            name=obj.replace("_", " ").title(),
            icon="mdi:led-variant-on",
            subscriptions=[(obj, "color_data")],
            color_mode=color_mode,
        )
        lights.append(desc)

    return lights

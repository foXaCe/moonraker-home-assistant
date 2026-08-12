"""Macro and service button description builders for the Moonraker integration."""

from __future__ import annotations


from ..const import METHODS
from ..coordinator import MoonrakerDataUpdateCoordinator
from .base import MoonrakerButtonDescription


async def build_macro_buttons(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerButtonDescription]:
    """Build macro button descriptions from the printer g-code help."""

    cmds = await coordinator.async_fetch_data(
        METHODS.PRINTER_GCODE_HELP, offline_ok=True
    )
    object_list = coordinator.objects_list or {"objects": []}
    object_names = (
        set(object_list.get("objects", [])) if isinstance(object_list, dict) else set()
    )
    macro_objects = {obj for obj in object_names if obj.startswith("gcode_macro ")}

    macros: list[MoonrakerButtonDescription] = []
    for cmd, desc in cmds.items():
        enable_by_default = False
        macro_object = None
        if desc == "G-Code macro":
            enable_by_default = False
        candidate_object = f"gcode_macro {cmd}"
        if candidate_object in macro_objects or (
            not macro_objects and desc == "G-Code macro"
        ):
            macro_object = candidate_object
            coordinator.add_query_objects(macro_object, None)

        macros.append(
            MoonrakerButtonDescription(
                key=cmd,
                name="Macro " + cmd.lower().replace("_", " ").title(),
                press_fn=lambda button: button.coordinator.async_send_data(
                    METHODS.PRINTER_GCODE_SCRIPT, {"script": button.invoke_name}
                ),
                icon="mdi:play",
                entity_registry_enabled_default=enable_by_default,
                macro_object=macro_object,
            )
        )

    # No refresh here: the config entry setup issues a single refresh once every
    # platform has subscribed its printer objects, which covers the macro
    # objects registered above.
    return macros


async def build_service_buttons(
    coordinator: MoonrakerDataUpdateCoordinator,
) -> list[MoonrakerButtonDescription]:
    """Build Start, Stop, and Restart button descriptions for all allowed services."""

    system_info = await coordinator.async_fetch_shared(
        METHODS.MACHINE_SYSTEM_INFO, offline_ok=True
    )
    available_services = system_info.get("system_info", {}).get(
        "available_services", []
    )

    service_buttons: list[MoonrakerButtonDescription] = []

    for service in available_services:
        # Stop button
        service_buttons.append(
            MoonrakerButtonDescription(
                key=f"stop_{service.lower()}",
                name=f"Arrêter {service}",
                press_fn=lambda button, svc=service: button.coordinator.async_send_data(
                    METHODS.MACHINE_SERVICES_STOP, {"service": svc}
                ),
                icon="mdi:stop-circle-outline",
                entity_registry_visible_default=False,
            )
        )

        # Start button
        service_buttons.append(
            MoonrakerButtonDescription(
                key=f"start_{service.lower()}",
                name=f"Démarrer {service}",
                press_fn=lambda button, svc=service: button.coordinator.async_send_data(
                    METHODS.MACHINE_SERVICES_START, {"service": svc}
                ),
                icon="mdi:play-circle-outline",
                entity_registry_visible_default=False,
            )
        )

        # Restart button
        service_buttons.append(
            MoonrakerButtonDescription(
                key=f"restart_{service.lower()}",
                name=f"Redémarrer {service}",
                press_fn=lambda button, svc=service: button.coordinator.async_send_data(
                    METHODS.MACHINE_SERVICES_RESTART, {"service": svc}
                ),
                icon="mdi:restart",
                entity_registry_visible_default=False,
            )
        )

    return service_buttons

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SCAN_INTERVAL
from .coordinator import FluidraCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    # Rate-limit deadline shared across coordinator recreations (setup retries,
    # reloads) so we don't keep hitting the API while we're being throttled.
    shared_state = domain_data.setdefault("_shared", {})

    coordinator = FluidraCoordinator(
        hass,
        entry,
        scan_interval=entry.options.get("scan_interval", SCAN_INTERVAL),
        shared_state=shared_state,
    )

    if entry.data.get("device_id"):
        # Device IDs are known, so entities can be built without a successful
        # first poll. Tolerate a rate-limited/failed start and self-heal at the
        # next interval instead of blocking setup and retrying aggressively.
        await coordinator.async_refresh()
    else:
        # No persisted device_id yet — we need one successful poll to build
        # stable entity unique_ids, so block setup until it succeeds.
        await coordinator.async_config_entry_first_refresh()

    domain_data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Only reload when the polling interval actually changed; writing resolved
    # device IDs back to entry.data also fires this listener and must not reload.
    coordinator: FluidraCoordinator = hass.data[DOMAIN][entry.entry_id]
    new_interval = entry.options.get("scan_interval", SCAN_INTERVAL)
    if new_interval != coordinator.scan_interval:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

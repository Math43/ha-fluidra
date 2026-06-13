import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import COGNITO_CLIENT_ID, COGNITO_REGION, DOMAIN, SCAN_INTERVAL
from .fluidra_client import FluidraAPIError, FluidraAuthError, FluidraClient, FluidraRateLimitError

_LOGGER = logging.getLogger(__name__)


class FluidraCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 scan_interval: int, shared_state: dict):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._entry = entry
        self.scan_interval = scan_interval
        self._client = FluidraClient(
            username=entry.data["username"],
            password=entry.data["password"],
            client_id=COGNITO_CLIENT_ID,
            region=COGNITO_REGION,
            session=async_get_clientsession(hass),
            pool_id=entry.data.get("pool_id"),
            device_id=entry.data.get("device_id"),
            shared_state=shared_state,
        )

    @property
    def device_id(self) -> str | None:
        return self._client.device_id

    async def _async_update_data(self) -> dict:
        try:
            data = await self._client.get_chlorinator_data()
        except FluidraRateLimitError as e:
            if self.data is not None:
                _LOGGER.warning("Fluidra rate limited (%ds) — returning cached data", e.retry_after)
                return self.data
            raise UpdateFailed(f"Rate limited with no cached data: {e}") from e
        except FluidraAuthError as e:
            raise UpdateFailed(f"Authentication error: {e}") from e
        except FluidraAPIError as e:
            raise UpdateFailed(f"API error: {e}") from e

        # Persist resolved device IDs so future startups skip the pools/devices
        # lookups and only call /components (1 request instead of 3).
        if not self._entry.data.get("device_id") and self._client.device_id:
            self.hass.config_entries.async_update_entry(
                self._entry,
                data={
                    **self._entry.data,
                    "pool_id": self._client.pool_id,
                    "device_id": self._client.device_id,
                },
            )

        return data

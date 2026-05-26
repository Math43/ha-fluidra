import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import COGNITO_CLIENT_ID, COGNITO_REGION, DOMAIN, SCAN_INTERVAL
from .fluidra_client import FluidraAPIError, FluidraAuthError, FluidraClient

_LOGGER = logging.getLogger(__name__)


class FluidraCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, username: str, password: str):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self._client = FluidraClient(
            username=username,
            password=password,
            client_id=COGNITO_CLIENT_ID,
            region=COGNITO_REGION,
            session=async_get_clientsession(hass),
        )

    @property
    def device_id(self) -> str | None:
        return self._client.device_id

    async def _async_update_data(self) -> dict:
        try:
            return await self._client.get_chlorinator_data()
        except FluidraAuthError as e:
            raise UpdateFailed(f"Authentication error: {e}") from e
        except FluidraAPIError as e:
            raise UpdateFailed(f"API error: {e}") from e

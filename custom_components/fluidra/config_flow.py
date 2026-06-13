import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import COGNITO_CLIENT_ID, COGNITO_REGION, DOMAIN, SCAN_INTERVAL
from .fluidra_client import FluidraAPIError, FluidraAuthError, FluidraClient


class FluidraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "FluidraOptionsFlow":
        return FluidraOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                client = FluidraClient(
                    username=user_input["username"],
                    password=user_input["password"],
                    client_id=COGNITO_CLIENT_ID,
                    region=COGNITO_REGION,
                    session=async_get_clientsession(self.hass),
                )
                await client.get_chlorinator_data()
            except FluidraAuthError:
                errors["base"] = "invalid_auth"
            except FluidraAPIError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                # Persist resolved IDs so the integration never has to call
                # /users/me/pools or /devices again (1 request per poll instead of 3).
                return self.async_create_entry(
                    title="Fluidra",
                    data={
                        **user_input,
                        "pool_id": client.pool_id,
                        "device_id": client.device_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str,
            }),
            errors=errors,
        )


class FluidraOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get("scan_interval", SCAN_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("scan_interval", default=current_interval): vol.All(
                    int, vol.Range(min=60, max=3600)
                ),
            }),
        )

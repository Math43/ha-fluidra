import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import COGNITO_CLIENT_ID, COGNITO_REGION, DOMAIN
from .fluidra_client import FluidraAPIError, FluidraAuthError, FluidraClient


class FluidraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
                return self.async_create_entry(title="Fluidra", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str,
            }),
            errors=errors,
        )

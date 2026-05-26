import asyncio
import aiohttp
import boto3
from datetime import datetime, timedelta


API_BASE = "https://api.fluidra-emea.com/generic"

COMPONENT_MAP = {
    10: "set_power",
    16: "set_ph",
    153: "value_power",
    165: "value_ph",
    172: "value_water_temperature",
    174: "value_salinity",
}


class FluidraAuthError(Exception):
    pass


class FluidraAPIError(Exception):
    pass


class FluidraClient:
    """Async client for the Fluidra EMEA API.

    Can be used standalone or injected with an existing aiohttp.ClientSession
    (Home Assistant pattern).
    """

    def __init__(self, username: str, password: str, client_id: str,
                 region: str = "eu-west-1", session: aiohttp.ClientSession = None):
        self._username = username
        self._password = password
        self._client_id = client_id
        self._region = region
        self._session = session
        self._owns_session = session is None

        self._id_token: str = None
        self._access_token: str = None
        self._refresh_token: str = None
        self._token_expiry: datetime = None

        self._pool_id: str = None
        self._device_id: str = None

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def pool_id(self) -> str | None:
        return self._pool_id

    # ── Session ──────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── Auth (boto3 via thread — non-blocking for the event loop) ────────────

    def _sync_authenticate(self) -> dict:
        cognito = boto3.client('cognito-idp', region_name=self._region)
        try:
            resp = cognito.initiate_auth(
                ClientId=self._client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={'USERNAME': self._username, 'PASSWORD': self._password},
            )
            return resp['AuthenticationResult']
        except cognito.exceptions.NotAuthorizedException as e:
            raise FluidraAuthError("Invalid credentials") from e
        except Exception as e:
            raise FluidraAuthError(str(e)) from e

    def _sync_refresh(self) -> dict:
        cognito = boto3.client('cognito-idp', region_name=self._region)
        resp = cognito.initiate_auth(
            ClientId=self._client_id,
            AuthFlow='REFRESH_TOKEN_AUTH',
            AuthParameters={'REFRESH_TOKEN': self._refresh_token},
        )
        return resp['AuthenticationResult']

    def _store_tokens(self, auth_result: dict):
        self._id_token = auth_result['IdToken']
        self._access_token = auth_result['AccessToken']
        if 'RefreshToken' in auth_result:
            self._refresh_token = auth_result['RefreshToken']
        # 60s buffer to avoid using a token right at expiry
        self._token_expiry = datetime.now() + timedelta(seconds=auth_result['ExpiresIn'] - 60)

    async def _authenticate(self):
        auth_result = await asyncio.to_thread(self._sync_authenticate)
        self._store_tokens(auth_result)

    async def _refresh(self):
        auth_result = await asyncio.to_thread(self._sync_refresh)
        self._store_tokens(auth_result)

    async def _ensure_auth(self):
        if self._id_token is None:
            await self._authenticate()
        elif datetime.now() >= self._token_expiry:
            await self._refresh()

    # ── API ───────────────────────────────────────────────────────────────────

    async def _get(self, path: str) -> dict | list:
        await self._ensure_auth()
        session = await self._get_session()
        headers = {'Authorization': f'Bearer {self._id_token}'}
        async with session.get(f"{API_BASE}{path}", headers=headers) as resp:
            if resp.status != 200:
                raise FluidraAPIError(f"HTTP {resp.status} on {path}")
            return await resp.json()

    async def _resolve_device(self):
        if self._pool_id is None:
            pools = await self._get("/users/me/pools?")
            self._pool_id = pools[0]['id']

        if self._device_id is None:
            devices = await self._get(f"/devices?poolId={self._pool_id}&format=tree")
            self._device_id = devices[0]['devices'][0]['id']

    # ── Public ────────────────────────────────────────────────────────────────

    async def get_chlorinator_data(self) -> dict:
        """Return normalized chlorinator sensor values."""
        await self._resolve_device()
        components = await self._get(f"/devices/{self._device_id}/components?deviceType=connected")

        raw = {
            COMPONENT_MAP[item['id']]: item['reportedValue']
            for item in components
            if item['id'] in COMPONENT_MAP
        }

        return {
            'set_power': raw.get('set_power'),
            'set_ph': raw['set_ph'] / 100 if 'set_ph' in raw else None,
            'value_power': raw.get('value_power'),
            'value_ph': raw['value_ph'] / 100 if 'value_ph' in raw else None,
            'value_water_temperature': raw['value_water_temperature'] / 10 if 'value_water_temperature' in raw else None,
            'value_salinity': raw.get('value_salinity'),
        }

    async def close(self):
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

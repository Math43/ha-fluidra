import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.fluidra-emea.com/generic"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
_MAX_RETRIES = 3

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


class FluidraRateLimitError(Exception):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class FluidraClient:
    """Async client for the Fluidra EMEA API."""

    def __init__(self, username: str, password: str, client_id: str,
                 region: str = "eu-west-1", session: aiohttp.ClientSession = None):
        self._username = username
        self._password = password
        self._client_id = client_id
        self._cognito_url = f"https://cognito-idp.{region}.amazonaws.com/"
        self._session = session
        self._owns_session = session is None

        self._id_token: str = None
        self._access_token: str = None
        self._refresh_token: str = None
        self._token_expiry: datetime = None
        self._rate_limited_until: datetime = None

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

    # ── Auth (direct Cognito HTTP API — fully async, no boto3) ───────────────

    async def _cognito_initiate_auth(self, auth_flow: str, auth_params: dict) -> dict:
        session = await self._get_session()
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        }
        payload = {
            "AuthFlow": auth_flow,
            "ClientId": self._client_id,
            "AuthParameters": auth_params,
        }
        async with session.post(
            self._cognito_url,
            json=payload,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                error_type = body.get("__type", "")
                if error_type in ("NotAuthorizedException", "UserNotFoundException"):
                    raise FluidraAuthError("Invalid credentials")
                raise FluidraAuthError(f"Cognito {error_type}: {body.get('message', '')}")
            return body["AuthenticationResult"]

    def _store_tokens(self, auth_result: dict):
        self._id_token = auth_result["IdToken"]
        self._access_token = auth_result["AccessToken"]
        if "RefreshToken" in auth_result:
            self._refresh_token = auth_result["RefreshToken"]
        # 60s buffer to avoid using a token right at expiry
        self._token_expiry = datetime.now() + timedelta(seconds=auth_result["ExpiresIn"] - 60)

    async def _authenticate(self):
        result = await self._cognito_initiate_auth(
            "USER_PASSWORD_AUTH",
            {"USERNAME": self._username, "PASSWORD": self._password},
        )
        self._store_tokens(result)

    async def _refresh(self):
        try:
            result = await self._cognito_initiate_auth(
                "REFRESH_TOKEN_AUTH",
                {"REFRESH_TOKEN": self._refresh_token},
            )
            self._store_tokens(result)
        except FluidraAuthError:
            # Refresh token expired or revoked, fall back to full re-auth
            await self._authenticate()

    async def _ensure_auth(self):
        if self._id_token is None:
            await self._authenticate()
        elif datetime.now() >= self._token_expiry:
            await self._refresh()

    # ── API ───────────────────────────────────────────────────────────────────

    async def _get(self, path: str) -> dict | list:
        # Bail early if still within a rate-limit window
        if self._rate_limited_until and datetime.now() < self._rate_limited_until:
            remaining = int((self._rate_limited_until - datetime.now()).total_seconds())
            raise FluidraRateLimitError(
                f"Rate limited until {self._rate_limited_until.isoformat()}",
                retry_after=remaining,
            )

        await self._ensure_auth()
        session = await self._get_session()

        for attempt in range(_MAX_RETRIES):
            headers = {"Authorization": f"Bearer {self._id_token}"}
            try:
                async with session.get(
                    f"{API_BASE}{path}",
                    headers=headers,
                    timeout=_REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status == 200:
                        self._rate_limited_until = None
                        return await resp.json()

                    if resp.status == 401:
                        # Token invalidated server-side; force re-auth once
                        self._id_token = None
                        await self._ensure_auth()
                        continue

                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 60))
                        self._rate_limited_until = datetime.now() + timedelta(seconds=retry_after)
                        raise FluidraRateLimitError(f"Rate limited on {path}", retry_after=retry_after)

                    if resp.status in (500, 502, 503, 504):
                        if attempt < _MAX_RETRIES - 1:
                            backoff = 5 * (attempt + 1)
                            _LOGGER.warning("Server error %d on %s, retrying in %ds", resp.status, path, backoff)
                            await asyncio.sleep(backoff)
                            continue

                    raise FluidraAPIError(f"HTTP {resp.status} on {path}")

            except aiohttp.ClientError as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(5)
                    continue
                raise FluidraAPIError(f"Request failed for {path}: {exc}") from exc

        raise FluidraAPIError(f"All retries exhausted for {path}")

    async def _resolve_device(self):
        if self._pool_id is None:
            pools = await self._get("/users/me/pools?")
            self._pool_id = pools[0]["id"]

        if self._device_id is None:
            devices = await self._get(f"/devices?poolId={self._pool_id}&format=tree")
            self._device_id = devices[0]["devices"][0]["id"]

    # ── Public ────────────────────────────────────────────────────────────────

    async def get_chlorinator_data(self) -> dict:
        """Return normalized chlorinator sensor values."""
        await self._resolve_device()
        components = await self._get(f"/devices/{self._device_id}/components?deviceType=connected")

        raw = {
            COMPONENT_MAP[item["id"]]: item["reportedValue"]
            for item in components
            if item["id"] in COMPONENT_MAP
        }

        return {
            "set_power": raw.get("set_power"),
            "set_ph": raw["set_ph"] / 100 if "set_ph" in raw else None,
            "value_power": raw.get("value_power"),
            "value_ph": raw["value_ph"] / 100 if "value_ph" in raw else None,
            "value_water_temperature": raw["value_water_temperature"] / 10 if "value_water_temperature" in raw else None,
            "value_salinity": raw["value_salinity"] / 100 if "value_salinity" in raw else None,
        }

    async def close(self):
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

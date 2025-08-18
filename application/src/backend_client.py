"""
Backend client for handling network communication and registration with the backend service.
"""

import socket
from enum import Enum
from typing import Any, Dict, Optional

import httpx
import sentry_sdk


class BackendState(Enum):
    """
    Backend states.
    """

    BACKEND_NOT_AVAILABLE = 0
    BACKEND_OK = 1
    BACKEND_ERROR_RESPONSE = 2
    BACKEND_EMPTY_RESPONSE = 3


class RegistrationState(Enum):
    """
    Application registration states.
    """

    REGISTRATION_FAILED = 0
    REGISTRATION_SUCCEEDED = 1


class BackendClient:
    """
    Handles all network communication with the backend service including
    registration, authentication, and data exchange.
    """

    def __init__(self):
        self.backend_url: Optional[str] = None
        self.registration_name: Optional[str] = None
        self.registration_key: Optional[str] = None
        self.update_sierra_items: bool = False

        # State tracking
        self.backend_state: BackendState = BackendState.BACKEND_NOT_AVAILABLE
        self.registration_state: RegistrationState = RegistrationState.REGISTRATION_FAILED

        # Network identity
        self.internal_hostname: str = socket.gethostname()
        self.internal_ip_address: Optional[str] = None

    def configure(
        self,
        backend_url: str,
        registration_name: str,
        registration_key: str,
        update_sierra_items: bool = False,
    ):
        """
        Configure the backend client with connection parameters.

        Args:
            backend_url: The backend API endpoint URL
            registration_name: The print station name/identifier
            registration_key: The API authentication key
            update_sierra_items: Whether to update Sierra items after printing
        """
        self.backend_url = backend_url
        self.registration_name = registration_name
        self.registration_key = registration_key
        self.update_sierra_items = update_sierra_items

    @classmethod
    def get_internal_ip(cls) -> Optional[str]:
        """
        Returns the internal IP address of the interface used for outbound connections.
        This is determined by creating a UDP socket to a public IP (e.g., 8.8.8.8).
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            return None

    def refresh_status_with_backend(self) -> bool:
        """
        Send status to backend and get backend status in response.
        Updates internal state based on the response.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.backend_url or not self.registration_key:
            self.backend_state = BackendState.BACKEND_NOT_AVAILABLE
            self.registration_state = RegistrationState.REGISTRATION_FAILED
            return False

        self.internal_hostname = socket.gethostname()
        self.internal_ip_address = self.__class__.get_internal_ip()

        try:
            data = {
                "internal_hostname": f"{self.internal_hostname}",
                "internal_ip_address": f"{self.internal_ip_address}",
            }
            response = httpx.post(
                f"{self.backend_url}/status",
                data=data,
                headers={
                    "x-api-key": self.registration_key,
                },
            )
            response.raise_for_status()
            self.backend_state = BackendState.BACKEND_OK
            self.registration_state = RegistrationState.REGISTRATION_SUCCEEDED
            return True
        except httpx.RequestError as e:
            # Backend had a protocol level error
            sentry_sdk.capture_exception(error=e)
            self.backend_state = BackendState.BACKEND_NOT_AVAILABLE
            self.registration_state = RegistrationState.REGISTRATION_FAILED
            return False
        except httpx.HTTPStatusError as e:
            # Backend did respond, but the response status was either 4xx or 5xx
            sentry_sdk.capture_exception(error=e)
            self.backend_state = BackendState.BACKEND_OK
            self.registration_state = RegistrationState.REGISTRATION_FAILED
            return False

    def get_item_data(self, item_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Fetch item data from the backend using the item identifier.

        Args:
            item_identifier: The primary item identifier (barcode)

        Returns:
            Dict containing item data if successful, None otherwise
        """
        if not self.backend_url or not self.registration_key:
            self.backend_state = BackendState.BACKEND_NOT_AVAILABLE
            return None

        try:
            response = httpx.get(
                f"{self.backend_url}/itemdata/{item_identifier}",
                headers={
                    "x-api-key": self.registration_key,
                },
            )
            response.raise_for_status()
            self.backend_state = BackendState.BACKEND_OK
            return response.json()
        except ValueError as e:
            # Response was missing required data fields
            sentry_sdk.capture_exception(error=e)
            self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
            return None
        except httpx.RequestError as e:
            # Backend had a protocol level error
            sentry_sdk.capture_exception(error=e)
            self.backend_state = BackendState.BACKEND_NOT_AVAILABLE
            return None
        except httpx.HTTPStatusError as e:
            # Backend did respond, but the response status was either 4xx or 5xx
            sentry_sdk.capture_exception(error=e)
            if e.response.status_code == 404:
                self.backend_state = BackendState.BACKEND_EMPTY_RESPONSE
            else:
                self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
            return None
        except Exception as e:
            # Error catchall
            sentry_sdk.capture_exception(error=e)
            self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
            return None

    def update_sierra_item(self, item_record_id: str) -> bool:
        """
        Update a Sierra item record after printing.

        Args:
            item_record_id: The Sierra item record ID

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.update_sierra_items or not self.backend_url or not self.registration_key:
            return True  # Skip if not configured to update

        try:
            response = httpx.put(
                f"{self.backend_url}/itemdata/{item_record_id}",
                headers={
                    "x-api-key": self.registration_key,
                },
            )
            response.raise_for_status()
            return True
        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            return False

    def is_backend_available(self) -> bool:
        """Check if backend is available and responsive."""
        return self.backend_state == BackendState.BACKEND_OK

    def is_registered(self) -> bool:
        """Check if the client is successfully registered with the backend."""
        return self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED

    def get_status_info(self) -> Dict[str, str]:
        """
        Get current status information for display.

        Returns:
            Dict containing hostname and IP address information
        """
        return {
            "hostname": self.internal_hostname,
            "ip_address": self.internal_ip_address or "Unknown",
        }

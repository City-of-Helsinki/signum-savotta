"""
Configuration Manager for Signum labeller application
"""

from configparser import RawConfigParser
from enum import Enum
from typing import Any, Dict, Optional

import sentry_sdk


class ConfigurationState(Enum):
    """
    Configuration states.
    """

    INVALID_CONFIGURATION = 0
    VALID_CONFIGURATION = 1


class ConfigurationManager:
    """
    Manages application configuration including reading, validation, and storage.
    """

    def __init__(self, config_file: str = "config.ini"):
        """
        Initialize the configuration manager.

        Args:
            config_file (str): Path to the configuration file
        """
        self.config_file = config_file
        self.configuration_state = ConfigurationState.INVALID_CONFIGURATION
        self._config_data: Dict[str, Any] = {}

        # Load configuration on initialization
        self.load_configuration()

    def load_configuration(self) -> bool:
        """
        Load configuration from the config file.

        Returns:
            bool: True if configuration was loaded successfully, False otherwise
        """
        try:
            config = RawConfigParser()
            with open(self.config_file, "r", encoding="utf-8") as configfile:
                config.read_file(configfile)

                # Extract backend configuration
                backend_url = config["backend"]["url"]
                update_sierra_items = config["backend"]["update_sierra_items"]

                # Extract registration configuration
                registration_name = config["registration"]["name"]
                registration_key = config["registration"]["key"]

                # Store configuration data
                self._config_data = {
                    "backend": {
                        "url": backend_url,
                        "update_sierra_items": update_sierra_items == "True",
                    },
                    "registration": {"name": registration_name, "key": registration_key},
                }

                # Load UI configuration with defaults
                self._load_ui_configuration(config)

                # Initialize Sentry if configuration exists
                try:
                    self._initialize_sentry(config)
                except Exception as e:
                    print(f"Sentry initialization failed: {e}")

                self.configuration_state = ConfigurationState.VALID_CONFIGURATION
                return True

        except Exception as e:
            print(f"Configuration loading failed: {e}")
            self.configuration_state = ConfigurationState.INVALID_CONFIGURATION
            return False

    def _initialize_sentry(self, config: RawConfigParser) -> None:
        """
        Initialize Sentry SDK with configuration.

        Args:
            config (RawConfigParser): The configuration parser instance
        """
        sentry_sdk.init(
            dsn=config["sentry"]["dsn"],
            environment=config["sentry"]["environment"],
            max_breadcrumbs=50,
            debug=False,
            traces_sample_rate=1.0,
            send_default_pii=True,
            release=config["sentry"]["release"],
        )

    def store_configuration(
        self, backend_url: str, registration_name: str, registration_key: str
    ) -> bool:
        """
        Store configuration information in the config file.
        Preserves existing configuration values that are not being updated.

        Args:
            backend_url (str): The backend URL
            registration_name (str): The print station name
            registration_key (str): The associated registration key

        Returns:
            bool: True if configuration was stored successfully, False otherwise
        """
        try:
            config = RawConfigParser()

            # Read existing configuration if file exists
            try:
                with open(self.config_file, "r", encoding="utf-8") as configfile:
                    config.read_file(configfile)
            except FileNotFoundError:
                # File doesn't exist yet, that's fine - we'll create it
                pass

            # Update only the specific values we want to change
            if "backend" not in config:
                config["backend"] = {}
            config["backend"]["url"] = backend_url

            if "registration" not in config:
                config["registration"] = {}
            config["registration"]["name"] = registration_name
            config["registration"]["key"] = registration_key

            # Write the complete configuration back to the file
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                config.write(configfile)

            # Update internal configuration data
            self._config_data.update(
                {
                    "backend": {
                        "url": backend_url,
                        "update_sierra_items": self._config_data.get("backend", {}).get(
                            "update_sierra_items", False
                        ),
                    },
                    "registration": {"name": registration_name, "key": registration_key},
                }
            )

            self.configuration_state = ConfigurationState.VALID_CONFIGURATION
            return True

        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            return False

    def get_backend_config(self) -> Optional[Dict[str, Any]]:
        """
        Get backend configuration.

        Returns:
            Optional[Dict[str, Any]]: Backend configuration or None if invalid
        """
        if self.configuration_state == ConfigurationState.VALID_CONFIGURATION:
            return self._config_data.get("backend")
        return None

    def get_registration_config(self) -> Optional[Dict[str, Any]]:
        """
        Get registration configuration.

        Returns:
            Optional[Dict[str, Any]]: Registration configuration or None if invalid
        """
        if self.configuration_state == ConfigurationState.VALID_CONFIGURATION:
            return self._config_data.get("registration")
        return None

    def is_valid(self) -> bool:
        """
        Check if configuration is valid.

        Returns:
            bool: True if configuration is valid, False otherwise
        """
        return self.configuration_state == ConfigurationState.VALID_CONFIGURATION

    def get_state(self) -> ConfigurationState:
        """
        Get the current configuration state.

        Returns:
            ConfigurationState: The current configuration state
        """
        return self.configuration_state

    def get_backend_url(self) -> Optional[str]:
        """
        Get backend URL from configuration.

        Returns:
            Optional[str]: Backend URL or None if invalid
        """
        backend_config = self.get_backend_config()
        return backend_config.get("url") if backend_config else None

    def get_registration_name(self) -> Optional[str]:
        """
        Get registration name from configuration.

        Returns:
            Optional[str]: Registration name or None if invalid
        """
        registration_config = self.get_registration_config()
        return registration_config.get("name") if registration_config else None

    def get_registration_key(self) -> Optional[str]:
        """
        Get registration key from configuration.

        Returns:
            Optional[str]: Registration key or None if invalid
        """
        registration_config = self.get_registration_config()
        return registration_config.get("key") if registration_config else None

    def should_update_sierra_items(self) -> bool:
        """
        Check if Sierra items should be updated.

        Returns:
            bool: True if Sierra items should be updated, False otherwise
        """
        backend_config = self.get_backend_config()
        return backend_config.get("update_sierra_items", False) if backend_config else False

    def _load_ui_configuration(self, config: RawConfigParser) -> None:
        """
        Load UI configuration with proper defaults and validation.

        Args:
            config (RawConfigParser): The configuration parser instance
        """
        # Default UI configuration values
        default_ui_config = {
            "update_interval_ms": 200,
            "state_stability_threshold": 3,
            "backend_refresh_interval": 10,
        }

        ui_config = {}

        if config.has_section("ui"):
            # Load and validate update interval
            try:
                interval = config.getint(
                    "ui", "update_interval_ms", fallback=default_ui_config["update_interval_ms"]
                )
                ui_config["update_interval_ms"] = self._validate_update_interval(interval)
            except (ValueError, TypeError):
                ui_config["update_interval_ms"] = default_ui_config["update_interval_ms"]

            # Load and validate state stability threshold
            try:
                threshold = config.getint(
                    "ui",
                    "state_stability_threshold",
                    fallback=default_ui_config["state_stability_threshold"],
                )
                ui_config["state_stability_threshold"] = max(
                    1, min(threshold, 5)
                )  # Clamp between 1-5
            except (ValueError, TypeError):
                ui_config["state_stability_threshold"] = default_ui_config[
                    "state_stability_threshold"
                ]

            # Load and validate backend refresh interval
            try:
                refresh_interval = config.getint(
                    "ui",
                    "backend_refresh_interval",
                    fallback=default_ui_config["backend_refresh_interval"],
                )
                ui_config["backend_refresh_interval"] = max(
                    1, min(refresh_interval, 40)
                )  # Clamp between 1-40
            except (ValueError, TypeError):
                ui_config["backend_refresh_interval"] = default_ui_config[
                    "backend_refresh_interval"
                ]
        else:
            # Use defaults if section doesn't exist
            ui_config = default_ui_config.copy()

        self._config_data["ui"] = ui_config

    def _validate_update_interval(self, interval: int) -> int:
        """
        Validate and adjust update interval to ensure reasonable performance.

        Args:
            interval (int): The proposed update interval in milliseconds

        Returns:
            int: A validated update interval

        Raises:
            ValueError: If interval is completely unreasonable
        """
        # Define reasonable bounds for UI update interval
        MIN_INTERVAL_MS = 100
        MAX_INTERVAL_MS = 200

        if not isinstance(interval, int):
            raise ValueError(f"Update interval must be an integer, got {type(interval)}")

        if interval <= 0:
            raise ValueError(f"Update interval must be positive, got {interval}")

        # Clamp to reasonable bounds
        if interval < MIN_INTERVAL_MS:
            print(
                f"Warning: UI update interval {interval}ms is too fast, using {MIN_INTERVAL_MS}ms"
            )
            return MIN_INTERVAL_MS
        elif interval > MAX_INTERVAL_MS:
            print(
                f"Warning: UI update interval {interval}ms is too slow, using {MAX_INTERVAL_MS}ms"
            )
            return MAX_INTERVAL_MS

        return interval

    def get_ui_config(self) -> Optional[Dict[str, Any]]:
        """
        Get UI configuration.

        Returns:
            Optional[Dict[str, Any]]: UI configuration or None if invalid
        """
        if self.configuration_state == ConfigurationState.VALID_CONFIGURATION:
            return self._config_data.get("ui")
        return None

    def get_ui_update_interval(self) -> int:
        """
        Get UI update interval from configuration.

        Returns:
            int: Update interval in milliseconds, defaults to 200ms
        """
        ui_config = self.get_ui_config()
        return ui_config.get("update_interval_ms", 200) if ui_config else 200

    def get_state_stability_threshold(self) -> int:
        """
        Get state stability threshold from configuration.

        Returns:
            int: State stability threshold, defaults to 3
        """
        ui_config = self.get_ui_config()
        return ui_config.get("state_stability_threshold", 3) if ui_config else 3

    def get_backend_refresh_interval(self) -> int:
        """
        Get backend refresh interval from configuration.

        Returns:
            int: Backend refresh interval in timer iterations, defaults to 10
        """
        ui_config = self.get_ui_config()
        return ui_config.get("backend_refresh_interval", 10) if ui_config else 10

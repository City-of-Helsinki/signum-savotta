"""
Configuration Manager for Signum labeller application
"""

from configparser import RawConfigParser
from enum import Enum
from typing import Any, Callable, Optional

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

    default_values = {
        "sentry": {
            "dsn": "",
            "environment": "",
            "release": "",
        },
        "backend": {"url": "http://127.0.0.1:8000", "update_sierra_items": False},
        "registration": {"name": "Not registered", "key": ""},
        "ui": {
            "update_interval_ms": 100,
            "state_stability_threshold": 1,
            "backend_refresh_interval": 10,
        },
        "printer": {"model": "QL-800", "label": "61"},
    }

    def __init__(self, config_file: str = "config.ini"):
        """
        Initialize the configuration manager.

        Args:
            config_file (str): Path to the configuration file
        """
        self.config_file = config_file
        self.configuration_state = ConfigurationState.INVALID_CONFIGURATION
        self._config = None

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

                has_correct_values = (
                    config["sentry"]["dsn"] != ""
                    and config["sentry"]["environment"] != ""
                    and config["sentry"]["release"] != ""
                    and config["backend"]["url"] != ""
                    and config["backend"]["update_sierra_items"] != ""
                    and config["registration"]["name"] != ""
                    and config["registration"]["key"] != ""
                    and config["ui"]["update_interval_ms"] != ""
                    and config["ui"]["state_stability_threshold"] != ""
                    and config["ui"]["backend_refresh_interval"] != ""
                    and config["printer"]["model"] != ""
                    and config["printer"]["label"] != ""
                )

                # Initialize Sentry if configuration exists
                try:
                    sentry_sdk.init(
                        dsn=config["sentry"]["dsn"],
                        environment=config["sentry"]["environment"],
                        max_breadcrumbs=50,
                        debug=False,
                        traces_sample_rate=1.0,
                        send_default_pii=True,
                        release=config["sentry"]["release"],
                    )
                except Exception as e:
                    print(f"Sentry initialization failed: {e}")

                if has_correct_values:
                    self._config = config
                    self.configuration_state = ConfigurationState.VALID_CONFIGURATION
                    return True

        except Exception as e:
            print(f"Configuration loading failed: {e}")
            self.configuration_state = ConfigurationState.INVALID_CONFIGURATION
            return False

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

            self.configuration_state = ConfigurationState.VALID_CONFIGURATION
            return True

        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            return False

    def get(self, section: str, option: str, asTypeFunc: Callable = lambda x: x) -> Optional[Any]:
        """
        Get configuration value.
        """
        try:
            if asTypeFunc:
                return asTypeFunc(self._config[section][option])
            else:
                return self._config[section][option]
        except Exception:
            try:
                return self.default_values[section][option]
            except Exception:
                return None

    def is_valid(self) -> bool:
        """
        Check if configuration is valid.

        Returns:
            bool: True if configuration is valid, False otherwise
        """
        return self.configuration_state == ConfigurationState.VALID_CONFIGURATION

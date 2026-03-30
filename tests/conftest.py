"""Configuration pytest – mock des dépendances HA pour les tests unitaires purs."""
from __future__ import annotations

import sys
import types


def _make_mock_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _stub_ha_modules() -> None:
    """Injecte des stubs minimalistes pour les modules HA non installés."""

    # voluptuous
    if "voluptuous" not in sys.modules:
        vol = _make_mock_module("voluptuous")
        vol.Schema   = lambda s, **kw: s
        vol.Optional = lambda k, **kw: k
        vol.Required = lambda k, **kw: k
        vol.All      = lambda *a, **kw: a[0] if a else None
        vol.Coerce   = lambda t: t
        vol.Range    = lambda **kw: None
        sys.modules["voluptuous"] = vol

    # homeassistant root – tous les modules importés par les fichiers testés
    ha_modules = {
        "homeassistant": {},
        "homeassistant.config_entries": {"ConfigEntry": type("ConfigEntry", (), {})},
        "homeassistant.const": {
            "Platform": type("Platform", (), {"SENSOR": "sensor", "BINARY_SENSOR": "binary_sensor"}),
            "UnitOfEnergy": type("UnitOfEnergy", (), {"KILO_WATT_HOUR": "kWh"}),
            "UnitOfMass": type("UnitOfMass", (), {"KILOGRAMS": "kg"}),
            "UnitOfTemperature": type("UnitOfTemperature", (), {"CELSIUS": "°C"}),
        },
        "homeassistant.core": {
            "HomeAssistant": type("HomeAssistant", (), {}),
            "ServiceCall": type("ServiceCall", (), {}),
            "callback": lambda f: f,
        },
        "homeassistant.helpers": {},
        "homeassistant.helpers.aiohttp_client": {
            "async_get_clientsession": lambda hass: None,
        },
        "homeassistant.helpers.device_registry": {
            "DeviceInfo": dict,
        },
        "homeassistant.helpers.entity_platform": {
            "AddEntitiesCallback": None,
        },
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": type("DataUpdateCoordinator", (), {
                "__class_getitem__": classmethod(lambda cls, item: cls),
                "__init__": lambda self, *a, **kw: None,
            }),
            "UpdateFailed": Exception,
            "CoordinatorEntity": type("CoordinatorEntity", (), {
                "__class_getitem__": classmethod(lambda cls, item: cls),
                "__init__": lambda self, *a, **kw: None,
            }),
        },
        "homeassistant.helpers.entity_registry": {
            "async_get": lambda hass: None,
            "async_entries_for_config_entry": lambda reg, eid: [],
        },
        "homeassistant.helpers.recorder": {
            "get_instance": lambda hass: None,
        },
        "homeassistant.components": {},
        "homeassistant.components.sensor": {
            "SensorDeviceClass": type("SensorDeviceClass", (), {
                "TEMPERATURE": "temperature", "ENERGY": "energy",
                "DATE": "date", "MONETARY": "monetary",
            }),
            "SensorEntity": object,
            "SensorEntityDescription": type("SensorEntityDescription", (), {}),
            "SensorStateClass": type("SensorStateClass", (), {
                "MEASUREMENT": "measurement", "TOTAL": "total",
                "TOTAL_INCREASING": "total_increasing",
            }),
        },
        "homeassistant.components.binary_sensor": {
            "BinarySensorDeviceClass": type("BinarySensorDeviceClass", (), {"PROBLEM": "problem"}),
            "BinarySensorEntity": object,
            "BinarySensorEntityDescription": type("BinarySensorEntityDescription", (), {}),
        },
        "homeassistant.components.recorder": {
            "get_instance": lambda hass: None,
        },
        "homeassistant.components.recorder.statistics": {
            "StatisticData": type("StatisticData", (), {"__init__": lambda self, **kw: None}),
            "StatisticMetaData": type("StatisticMetaData", (), {"__init__": lambda self, **kw: None}),
            "StatisticMeanType": type("StatisticMeanType", (), {"ARITHMETIC": "arithmetic", "NONE": "none"}),
            "async_add_external_statistics": lambda *a, **kw: None,
            "async_import_statistics": lambda *a, **kw: None,
        },
        "homeassistant.components.recorder.models": {},
        "homeassistant.util": {},
        "homeassistant.util.dt": {
            "get_default_time_zone": lambda: __import__("datetime").timezone.utc,
        },
    }
    for mod_name, attrs in ha_modules.items():
        if mod_name not in sys.modules:
            sys.modules[mod_name] = _make_mock_module(mod_name, **attrs)
        else:
            for k, v in attrs.items():
                if not hasattr(sys.modules[mod_name], k):
                    setattr(sys.modules[mod_name], k, v)



_stub_ha_modules()

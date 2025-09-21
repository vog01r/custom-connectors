"""Custom Connectors for Treasure Data.

Collection de connecteurs personnalisés pour l'ingestion de données
dans Treasure Data depuis diverses sources externes.
"""

__version__ = "1.0.0"
__author__ = "Treasure Data"
__email__ = "engineering@treasuredata.com"

# Re-export des classes principales pour faciliter l'importation
from custom_connectors.core.exceptions import (
    ConnectorError,
    ConfigurationError,
    APIError,
    RetryableError,
)

__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "ConnectorError",
    "ConfigurationError", 
    "APIError",
    "RetryableError",
]

"""Configuration globale des tests pytest."""

import os
import pytest
from unittest.mock import Mock
from typing import Generator, Dict, Any


# Configuration des variables d'environnement pour les tests
@pytest.fixture(autouse=True)
def setup_test_env() -> Generator[None, None, None]:
    """Configure l'environnement de test."""
    # Sauvegarde des variables d'environnement existantes
    original_env = dict(os.environ)
    
    # Variables d'environnement de test
    test_env = {
        "YOTPO_CLIENT_SECRET": "test_secret",
        "YOTPO_STORE_ID": "test_store_123",
        "TD_API_KEY": "test_td_key",
        "TD_DATABASE": "test_database",
        "TD_TABLE": "test_table",
    }
    
    # Application des variables de test
    os.environ.update(test_env)
    
    yield
    
    # Restauration de l'environnement original
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_requests() -> Mock:
    """Mock pour les requêtes HTTP."""
    return Mock()


@pytest.fixture
def sample_yotpo_customer() -> Dict[str, Any]:
    """Exemple de données client Yotpo."""
    return {
        "id": "customer_123",
        "email": "test@example.com",
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z",
        "first_name": "John",
        "last_name": "Doe",
        "phone": "+1234567890",
        "loyalty": {
            "points": 100,
            "tier": "bronze",
            "status": "active",
        },
        "custom_properties": {
            "source": "website",
            "preferences": {"newsletter": True},
        },
    }


@pytest.fixture
def sample_yotpo_response(sample_yotpo_customer: Dict[str, Any]) -> Dict[str, Any]:
    """Exemple de réponse API Yotpo."""
    return {
        "customers": [sample_yotpo_customer],
        "pagination": {
            "next_page_info": "next_page_token_123",
            "has_more": True,
        },
    }


@pytest.fixture
def mock_td_client() -> Mock:
    """Mock pour le client Treasure Data."""
    client = Mock()
    client.load_table_from_dataframe.return_value = None
    client.close.return_value = None
    return client

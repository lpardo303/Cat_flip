"""Fixtures compartidos: aislar el estado global de `app` entre tests.

`app.py` guarda el DataFrame y el pipeline en globals de módulo
(`current_df`, `history`, `code_log`, `op_history`, `redo_history`). Sin este reset, los tests se
contaminan entre sí (el orden de ejecución importaba).
"""
import pytest

import app as app_module


@pytest.fixture(autouse=True)
def reset_app_state():
    """Pone el estado global en cero antes de cada test y lo restaura al salir."""
    app_module.current_df = None
    app_module.history = []
    app_module.code_log = []
    app_module.op_history = []
    app_module.redo_history = []
    app_module.right_df = None
    app_module.right_name = ""
    app_module.right_code = ""
    yield
    app_module.current_df = None
    app_module.history = []
    app_module.code_log = []
    app_module.op_history = []
    app_module.redo_history = []
    app_module.right_df = None
    app_module.right_name = ""
    app_module.right_code = ""


@pytest.fixture()
def client():
    """Cliente de prueba de Flask con el estado ya limpio."""
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()

# tests/test_mqtt_client.py
"""
Tests unitaires pour Model/MQTTClient.py.

paho.mqtt est entièrement simulé pour ne nécessiter aucun broker réel.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call
import sys

# ── Stub paho ─────────────────────────────────────────────────────────────────
mock_paho       = MagicMock()
mock_mqtt_mod   = MagicMock()
mock_client_cls = MagicMock()
mock_client_ins = MagicMock()
mock_client_cls.return_value    = mock_client_ins
mock_client_ins.publish.return_value = (0, 1)   # MQTT_ERR_SUCCESS
mock_mqtt_mod.Client            = mock_client_cls
mock_mqtt_mod.MQTT_ERR_SUCCESS  = 0
mock_paho.mqtt                  = mock_mqtt_mod
mock_paho.mqtt.client           = mock_mqtt_mod
sys.modules['paho']             = mock_paho
sys.modules['paho.mqtt']        = mock_mqtt_mod
sys.modules['paho.mqtt.client'] = mock_mqtt_mod

# Stub ssl
mock_ssl = MagicMock()
mock_ssl.PROTOCOL_TLS = 2
sys.modules['ssl'] = mock_ssl

from ..Model.MQTTClient import MQTTClient  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_mock():
    mock_client_ins.reset_mock()
    mock_client_ins.publish.return_value = (0, 1)
    yield


@pytest.fixture
def client():
    with patch('uuid.getnode', return_value=0xAABBCCDDEEFF):
        return MQTTClient(
            broker="test.broker",
            port=8883,
            topic_base="test/sondes/",
            username="marais2026",
            password="hyrome49#",
            ca_cert="ca.crt"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Construction et connexion
# ─────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_connect_appele(self, client):
        mock_client_ins.connect.assert_called()

    def test_loop_start_appele(self, client):
        mock_client_ins.loop_start.assert_called()

    def test_mac_dans_topic_pm10(self, client):
        assert "AA:BB:CC:DD:EE:FF" in client._topic_pm10

    def test_mac_dans_topic_tvoc(self, client):
        assert "AA:BB:CC:DD:EE:FF" in client._topic_tvoc

    def test_topic_pm10_contient_pm10(self, client):
        assert "pm10" in client._topic_pm10

    def test_topic_tvoc_contient_tvoc(self, client):
        assert "tvoc_co2" in client._topic_tvoc

    def test_credentials_configures(self, client):
        mock_client_ins.username_pw_set.assert_called_with("user", "pass")

    def test_tls_configure(self, client):
        mock_client_ins.tls_set.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# publish_pm10
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishPm10:
    def test_retourne_true_si_succes(self, client):
        mock_client_ins.publish.return_value = (0, 1)
        assert client.publish_pm10(42.5) is True

    def test_retourne_false_si_echec(self, client):
        mock_client_ins.publish.return_value = (1, 0)   # code erreur ≠ 0
        assert client.publish_pm10(42.5) is False

    def test_payload_contient_pm10(self, client):
        client.publish_pm10(77.3)
        _, kwargs = mock_client_ins.publish.call_args
        # Le payload est le 2e argument positionnel
        args = mock_client_ins.publish.call_args[0]
        payload = json.loads(args[1])
        assert payload["mesure"]["PM 10"] == pytest.approx(77.3)

    def test_payload_contient_timestamp(self, client):
        client.publish_pm10(10.0)
        args = mock_client_ins.publish.call_args[0]
        payload = json.loads(args[1])
        assert "timestamp" in payload

    def test_publication_sur_bon_topic(self, client):
        client.publish_pm10(1.0)
        args = mock_client_ins.publish.call_args[0]
        assert args[0] == client._topic_pm10

    def test_pm10_zero(self, client):
        assert client.publish_pm10(0.0) is True


# ─────────────────────────────────────────────────────────────────────────────
# publish_tvoc_co2
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishTvocCo2:
    def test_retourne_true_si_succes(self, client):
        mock_client_ins.publish.return_value = (0, 1)
        assert client.publish_tvoc_co2(850, 320) is True

    def test_retourne_false_si_echec(self, client):
        mock_client_ins.publish.return_value = (4, 0)
        assert client.publish_tvoc_co2(850, 320) is False

    def test_payload_eco2_correct(self, client):
        client.publish_tvoc_co2(600, 150)
        args = mock_client_ins.publish.call_args[0]
        payload = json.loads(args[1])
        assert payload["mesure"]["ECO2"] == 600

    def test_payload_tvoc_correct(self, client):
        client.publish_tvoc_co2(600, 150)
        args = mock_client_ins.publish.call_args[0]
        payload = json.loads(args[1])
        assert payload["mesure"]["TVOC"] == 150

    def test_publication_sur_bon_topic(self, client):
        client.publish_tvoc_co2(400, 0)
        args = mock_client_ins.publish.call_args[0]
        assert args[0] == client._topic_tvoc

    def test_payload_contient_timestamp(self, client):
        client.publish_tvoc_co2(400, 0)
        args = mock_client_ins.publish.call_args[0]
        payload = json.loads(args[1])
        assert "timestamp" in payload


# ─────────────────────────────────────────────────────────────────────────────
# subscribe_seuils
# ─────────────────────────────────────────────────────────────────────────────

class TestSubscribeSeuils:
    def test_abonnement_au_topic(self, client):
        cb = MagicMock()
        client.subscribe_seuils("marais/sondes/seuils", cb)
        mock_client_ins.subscribe.assert_called_with("marais/sondes/seuils")

    def test_callback_enregistre(self, client):
        cb = MagicMock()
        client.subscribe_seuils("topic/test", cb)
        assert client._cb_seuils is cb

    def test_topic_seuils_memorise(self, client):
        client.subscribe_seuils("topic/abc", MagicMock())
        assert client._topic_seuils == "topic/abc"


# ─────────────────────────────────────────────────────────────────────────────
# _on_message (parsing des seuils)
# ─────────────────────────────────────────────────────────────────────────────

class TestOnMessage:
    def _make_msg(self, payload: dict):
        msg = MagicMock()
        msg.payload = json.dumps(payload).encode('utf-8')
        return msg

    def test_callback_appele_avec_bons_seuils(self, client):
        cb = MagicMock()
        client._cb_seuils = cb
        msg = self._make_msg({"pm10_alerte_seuil": 25.0, "pm10_danger_seuil": 50.0})
        client._on_message(None, None, msg)
        cb.assert_called_once_with(25.0, 50.0)

    def test_callback_non_appele_si_json_invalide(self, client):
        cb = MagicMock()
        client._cb_seuils = cb
        msg = MagicMock()
        msg.payload = b"pas du json {"
        client._on_message(None, None, msg)
        cb.assert_not_called()

    def test_callback_non_appele_si_cle_manquante(self, client):
        cb = MagicMock()
        client._cb_seuils = cb
        msg = self._make_msg({"seuil_vert": 10.0})   # seuil_orange absent
        client._on_message(None, None, msg)
        cb.assert_not_called()

    def test_pas_d_appel_si_cb_none(self, client):
        client._cb_seuils = None
        msg = self._make_msg({"seuil_vert": 10.0, "seuil_orange": 20.0})
        # Ne doit pas lever d'exception
        client._on_message(None, None, msg)

    def test_seuils_convertis_en_float(self, client):
        cb = MagicMock()
        client._cb_seuils = cb
        msg = self._make_msg({"seuil_vert": "15", "seuil_orange": "35"})
        client._on_message(None, None, msg)
        cb.assert_called_once_with(15.0, 35.0)


# ─────────────────────────────────────────────────────────────────────────────
# _on_connect
# ─────────────────────────────────────────────────────────────────────────────

class TestOnConnect:
    def test_reabonnement_apres_reconnexion(self, client):
        client._topic_seuils = "marais/seuils/config"
        mock_client_ins.reset_mock()
        client._on_connect(mock_client_ins, None, None, rc=0)
        mock_client_ins.subscribe.assert_called_with("marais/seuils/config")

    def test_pas_de_reabonnement_sans_topic_seuils(self, client):
        client._topic_seuils = None
        mock_client_ins.reset_mock()
        client._on_connect(mock_client_ins, None, None, rc=0)
        mock_client_ins.subscribe.assert_not_called()

    def test_pas_de_reabonnement_si_rc_non_zero(self, client):
        client._topic_seuils = "topic"
        mock_client_ins.reset_mock()
        client._on_connect(mock_client_ins, None, None, rc=1)
        mock_client_ins.subscribe.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# disconnect
# ─────────────────────────────────────────────────────────────────────────────

class TestDisconnect:
    def test_loop_stop_appele(self, client):
        mock_client_ins.reset_mock()
        client.disconnect()
        mock_client_ins.loop_stop.assert_called_once()

    def test_disconnect_appele(self, client):
        mock_client_ins.reset_mock()
        client.disconnect()
        mock_client_ins.disconnect.assert_called_once()

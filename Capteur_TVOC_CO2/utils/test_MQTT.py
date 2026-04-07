import unittest
from unittest.mock import patch, MagicMock
from MQTT import MQTT


class TestMQTT(unittest.TestCase):

    @patch("MQTT.mqtt.Client")
    def test_init(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        obj = MQTT()

        self.assertIsNotNone(obj)
        mock_client.connect.assert_called()

    @patch("MQTT.mqtt.Client")
    def test_publish(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        obj = MQTT()

        if hasattr(obj, "publish"):
            obj.publish("bonjour")
            mock_client.publish.assert_called()
        elif hasattr(obj, "publier"):
            obj.publier("bonjour")
            mock_client.publish.assert_called()

    @patch("MQTT.mqtt.Client")
    def test_subscribe(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        obj = MQTT()

        def callback(client, userdata, msg):
            pass

        if hasattr(obj, "subscribe"):
            obj.subscribe(callback)
            mock_client.subscribe.assert_called()
        elif hasattr(obj, "abonner"):
            obj.abonner(callback)
            mock_client.subscribe.assert_called()


if __name__ == "__main__":
    unittest.main()

import base64
import io
import json
import os
import threading
import ssl
import socket
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import server


def request_data(**changes):
    data = {"consent": True, "orientation": "normal", "recheck": False,
            "image": "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xfftest\xff\xd9").decode()}
    data.update(changes)
    return data


def observation(**changes):
    value = {"status": "adjust", "image_side": "left", "region": "corner", "observation": "画面左侧嘴角边缘外有明显红色。"}
    value.update(changes)
    return value


def quality(**changes):
    value = {key: True for key in server.QUALITY_FIELDS if key != 'reason'}
    value.update(occluded=False, reason='ok')
    value.update(changes)
    return value


def reply(value):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]}).encode())


class AnalysisTests(unittest.TestCase):
    def test_direction(self):
        for side in ["left", "right"]:
            for direction in ["normal", "mirrored"]:
                result = server.format_result(observation(image_side=side), direction, False, "test")
                expected = side if direction == "mirrored" else {"left": "right", "right": "left"}[side]
                self.assertIn("左侧" if expected == "left" else "右侧", result["guidance"])

    def test_uncertain_location(self):
        for changes in [{"image_side": "unknown"}, {"region": "unknown"}, {"image_side": "center"}]:
            self.assertEqual(server.format_result(observation(**changes), "normal", False, "test")["status"], "uncertain")

    def test_recheck_no_improvement_claim(self):
        result = server.format_result(observation(status="clear", image_side="unknown", region="unknown"), "normal", True, "test")
        self.assertNotIn("改善", result["title"])
        self.assertIn("未比较", result["evidence"])

    def test_invalid_input(self):
        for changes in [{"consent": False}, {"orientation": "unknown"}, {"recheck": 1}, {"image": "https://example.com/a.jpg"}, {"image": "data:image/jpeg;base64,@@"}]:
            with self.assertRaises(server.Problem):
                server.validate_input(request_data(**changes))

    def test_invalid_result(self):
        for value in [None, {}, observation(status="success"), observation(observation="x" * 181)]:
            with self.assertRaises(server.Problem):
                server.format_result(value, "normal", False, "test")

    def test_provider_payload(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch("urllib.request.urlopen", side_effect=[reply(quality()), reply(observation())]) as call:
            result = server.analyze(request_data())
        payload = json.loads(call.call_args.args[0].data)
        self.assertEqual(result["mode"], "ai")
        self.assertEqual(payload["provider"]["data_collection"], "deny")
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")
        self.assertNotIn("test-key", json.dumps(result))
        self.assertEqual(call.call_count, 2)
        first = json.loads(call.call_args_list[0].args[0].data)
        self.assertEqual(first['response_format']['json_schema']['name'], 'photo_visibility')

    def test_visibility_gate(self):
        cases = [(quality(occluded=True), 'occluded'), (quality(right_corner_visible=False), 'incomplete'),
                 (quality(sharp_enough=False), 'blur'), (quality(lit_enough=False), 'dark'),
                 (quality(reason='ambiguous'), 'ambiguous')]
        for value, reason in cases:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch('urllib.request.urlopen', return_value=reply(value)) as call:
                result = server.analyze(request_data())
            self.assertEqual(result['status'], 'uncertain')
            self.assertEqual(result['reason'], reason)
            self.assertEqual(call.call_count, 1, 'Gate failure must not invoke lipstick analysis')
            self.assertNotIn('棉签', result['guidance'])

    def test_visible_overflow_reaches_lipstick_analysis(self):
        # Contract regression only: mocked responses do not establish model accuracy.
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch('urllib.request.urlopen', side_effect=[reply(quality()), reply(observation())]) as call:
            result = server.analyze(request_data())
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result['status'], 'adjust')
        self.assertIn('你自己的右侧', result['guidance'])
        self.assertEqual(result['quality_check'], quality())
        payload = json.loads(call.call_args_list[0].args[0].data)
        self.assertIn('NOT cropping', payload['messages'][0]['content'])

    def test_invalid_quality_fails_closed(self):
        for value in [{}, quality(occluded='false'), quality(reason='success'), quality(right_corner_visible=1)]:
            with self.assertRaises(server.Problem): server.validate_quality(value)

    def test_reason_specific_guidance(self):
        for reason, text in [('occluded', '移开'), ('blur', '对焦'), ('dark', '光源'), ('incomplete', '入')]:
            value = server.format_result(observation(status='clear'), 'normal', False, 'test', reason)
            self.assertEqual(value['status'], 'uncertain')
            self.assertIn(text, value['guidance'])

    def test_no_untrusted_prose_in_display(self):
        value = server.format_result(observation(observation='Left corner improved. 很好。'), 'normal', True, 'test')
        display = value['title'] + value['guidance'] + value['evidence']
        self.assertNotIn('Left', display)
        self.assertNotIn('改善', display)
        self.assertNotIn('左侧', display)
        self.assertIn('你自己的右侧', display)

    def test_connection_error_types(self):
        for cause, label in [(ssl.SSLCertVerificationError('certificate'), '证书'), (socket.gaierror('dns'), 'DNS')]:
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'}), patch('urllib.request.urlopen', side_effect=urllib.error.URLError(cause)):
                with self.assertRaises(server.Problem) as caught: server.analyze(request_data())
            self.assertIn(label, caught.exception.message)

    def test_upstream_errors(self):
        for code in [401, 402, 403, 429, 500]:
            error = urllib.error.HTTPError("", code, "error", {}, None)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(server.Problem) as caught:
                    server.analyze(request_data())
                self.assertNotIn("test-key", caught.exception.message)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.origin = "http://127.0.0.1:" + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()

    def test_no_secret_or_source_files(self):
        for path in ["/.env.local", "/server.py", "/README.md", "/assets/../../server.py"]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.origin + path)
            self.assertEqual(caught.exception.code, 404)

    def test_reject_foreign_origin(self):
        req = urllib.request.Request(self.origin + "/api/analyze", data=b"{}", headers={"Origin": "https://other.example", "X-Local-Token": server.TOKEN, "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code, 403)

    def test_missing_key_clear_error(self):
        req = urllib.request.Request(self.origin + "/api/analyze", data=json.dumps(request_data()).encode(), headers={"Origin": self.origin, "X-Local-Token": server.TOKEN, "Content-Type": "application/json"})
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code, 503)
            self.assertIn("尚未配置", json.loads(caught.exception.read())["error"])

    def test_home(self):
        with urllib.request.urlopen(self.origin) as response:
            self.assertIn(b"send-consent", response.read())


if __name__ == "__main__":
    unittest.main()

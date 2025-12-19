from __future__ import annotations

import json
from typing import Any, Dict, List

import requests
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request


MULTI_MODAL_PATH = "/api/vikingdb/data/search/multi_modal"


class VikingDBDataClient:
    def __init__(self, ak: str, sk: str, host: str, region: str, service: str, timeout_s: int) -> None:
        self.ak = ak
        self.sk = sk
        self.host = host
        self.region = region
        self.service = service
        self.timeout_s = timeout_s

    def _prepare_request(self, method: str, path: str, body: Dict[str, Any]) -> Request:
        r = Request()
        r.set_shema("https")
        r.set_method(method.upper())
        r.set_connection_timeout(self.timeout_s)
        r.set_socket_timeout(self.timeout_s)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Host": self.host,
        }
        r.set_headers(headers)
        r.set_host(self.host)
        r.set_path(path)
        r.set_body(json.dumps(body, ensure_ascii=False))

        credentials = Credentials(self.ak, self.sk, self.service, self.region)
        SignerV4.sign(r, credentials)
        return r

    def post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        req = self._prepare_request("POST", path, body)
        url = f"https://{self.host}{req.path}"
        resp = requests.post(url, headers=req.headers, data=req.body, timeout=self.timeout_s)

        if resp.status_code // 100 != 2:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        try:
            return resp.json()
        except Exception:
            raise RuntimeError(f"Non-JSON response: {resp.text}")


def build_influencer_filter(influencer: str) -> Dict[str, Any]:
    return {
        "op": "and",
        "conds": [
            {
                "op": "must",
                "field": "influencer",
                "conds": [influencer],
            }
        ],
    }


def parse_output_fields(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]



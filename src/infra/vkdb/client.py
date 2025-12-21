from __future__ import annotations

import json
from typing import Any, Dict, List

import requests
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request


MULTI_MODAL_PATH = "/api/vikingdb/data/search/multi_modal"
RANDOM_PATH = "/api/vikingdb/data/search/random"


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
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        }
        r.set_headers(headers)
        r.set_host(self.host)
        r.set_path(path)
        r.set_body(json.dumps(body, ensure_ascii=False))

        credentials = Credentials(self.ak, self.sk, self.service, self.region)
        SignerV4.sign(r, credentials)
        return r

    def post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        import time
        import hashlib
        logger = logging.getLogger(__name__)
        
        req = self._prepare_request("POST", path, body)
        url = f"https://{self.host}{req.path}"
        
        # 计算请求体的hash（用于诊断缓存问题）
        # 排除_request_id来计算"有效请求参数"的hash
        body_for_hash = {k: v for k, v in body.items() if k != "_request_id"}
        body_json_for_hash = json.dumps(body_for_hash, ensure_ascii=False, sort_keys=True)
        body_hash = hashlib.md5(body_json_for_hash.encode('utf-8')).hexdigest()[:8]
        
        # 记录请求时间戳和URL用于诊断
        request_start = time.time()
        logger.info(f"🌐 [VikingDB HTTP] 发送请求到: {url}")
        logger.info(f"🌐 [VikingDB HTTP] 请求时间戳: {request_start:.3f}")
        logger.info(f"🔍 [缓存诊断] 有效请求参数hash (排除_request_id): {body_hash}")
        logger.info(f"🔍 [缓存诊断] 请求体大小: {len(req.body)} 字节")
        
        resp = requests.post(url, headers=req.headers, data=req.body, timeout=self.timeout_s)
        
        request_end = time.time()
        elapsed = request_end - request_start
        logger.info(f"🌐 [VikingDB HTTP] 响应时间: {elapsed:.3f}s, 状态码: {resp.status_code}")
        logger.info(f"🔍 [缓存诊断] 响应时间分析: {'⚠️ 可能缓存' if elapsed < 0.1 else '✅ 正常检索'} (<0.1s可能是缓存)")

        if resp.status_code // 100 != 2:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        try:
            result = resp.json()
            
            # 记录返回结果的完整ID列表用于诊断缓存问题
            if isinstance(result, dict):
                data_list = result.get("result", {}).get("data", [])
                if data_list:
                    # 记录所有结果的ID（不只是前10个）
                    result_ids = [item.get("id", "unknown") for item in data_list]
                    result_ids_hash = hashlib.md5(",".join(result_ids).encode('utf-8')).hexdigest()[:8]
                    logger.info(f"🔍 [缓存诊断] 返回结果总数: {len(data_list)}")
                    logger.info(f"🔍 [缓存诊断] 返回结果ID列表（前10个）: {result_ids[:10]}")
                    logger.info(f"🔍 [缓存诊断] 返回结果ID列表hash: {result_ids_hash} (用于对比多次请求)")
                    logger.info(f"🔍 [缓存诊断] 完整结果ID列表: {result_ids}")
                else:
                    logger.info(f"🔍 [缓存诊断] 返回结果为空")
            
            return result
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



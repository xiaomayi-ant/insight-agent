
<span id="f2dafdaa"></span>
# 概述
多模态数据检索是指向量数据库支持直接通过图文等多模态数据类型进行检索，且支持模态的组合，如文搜图，图搜图，图搜文+图等。
<span id="f07090fb"></span>
# 请求接口
:::tip
请求向量数据库 VikingDB 的 OpenAPI 接口时，可以使用 **ak、sk** **构造签名**进行鉴权。请参见[数据面API调用流程](/docs/84313/1791125)，复制调用示例并填入必要信息
:::

| | | | \
|URI |/api/vikingdb/data/search/multi_modal |统一资源标识符 |
|---|---|---|
| | | | \
|方法 |POST |客户端对向量数据库服务器请求的操作类型 |
| | | | \
|请求头 |Content-Type: application/json |请求消息类型 |
|^^| | | \
| |Authorization: HMAC-SHA256 *** |鉴权 |


<span id="ea7eebb8"></span>
# 请求体参数
仅列出本接口特有的参数。更多信息请参见[检索公共参数](/docs/84313/1791133)。

| | | | | \
|参数名 |必选 |类型 |备注 |
|---|---|---|---|
| | | | | \
|text |至少选1 |string |检索的文本内容 |
| |^^| | | \
|image | |string |* 图片tos链接。`tos://{bucket}/{object}` |\
| | | |* http/https格式链接 |
| |^^| | | \
|video | |map |{ |\
| | | |"value": tos链接，http/https格式链接 （该字段必填） |\
| | | |"fps": 2.0 (0.2-5，该字段选填) |\
| | | |} |
| | | | | \
|need_instruction |若模型支持instruction能力，则此参数必填。 |bool |带文本的检索，可以在返回结果里real_text_query参数，查看实际生效的检索语句。 |\
| | | |模型列表参考：[向量化计算-Embedding](https://www.volcengine.com/docs/84313/1791161?lang=zh) |\
| | | |> 开启后将增加默认的Instruction一起检索，V2版本 控制台默认关闭。 |


<span id="5291ffac"></span>
# 请求响应示例
<span id="390e1fb7"></span>
## 1.文本检索

* 请求参数

```JSON
req_path = "/api/vikingdb/data/search/multi_modal"
req_body = {
    "collection_name": "test_coll_with_vectorize",
    "index_name": "idx_1",
    "text": "向量是指在数学中具有一定大小和方向的量，文本、图片、音视频等非结构化数据",
    "need_instruction": true,
    "output_fields": [
        "f_text"
    ],
    "limit": 2
}
```


* 响应参数

```JSON
{
    "code": "Success",
    "message": "The API call was executed successfully.",
    "request_id": "02175438839168500000000000000000000ffff0a003ee4fc3499",
    "result": {
        "data": [
            {
                "id": "uid_001",
                "fields": {
                    "f_text": "向量是指在数学中具有一定大小和方向的量"
                },
                "score": 9.899999618530273,
                "ann_score": 9.899999618530273
            },
            {
                "id": "uid_002",
                "fields": {
                    "f_text": "向量是高中数学里的一个重要概念"
                },
                "score": 8.324234999961,
                "ann_score": 8.324234999961,
            }
        ],
        "total_return_count": 2,
        "real_text_query": "根据这个问题，找到能回答这个问题的相应文本或图片：向量是指在数学中具有一定大小和方向的量，文本、图片、音视频等非结构化数据",
        "token_usage": {
            "doubao-embedding-vision__250328": {
                "prompt_tokens":53,
                "completion_tokens":0,
                "image_tokens":0,
                "total_tokens":53
            }
        }
    }
}
```


<span id="90e646da"></span>
## 2.文本+图片检索

* 请求参数

```JSON
req_path = "/api/vikingdb/data/search/multi_modal"
req_body = {
    "collection_name": "test_coll_with_vectorize",
    "index_name": "idx_1",
    "text": "向量是指在数学中具有一定大小和方向的量，文本、图片、音视频等非结构化数据",
    "image": "tos://my_bucket/vector_icon.jpg",
    "output_fields": [
        "f_text", "f_image"
    ],
    "need_instruction": true,
    "limit": 2
}
```


* 响应参数

```JSON
{
    "code": "Success",
    "message": "The API call was executed successfully.",
    "request_id": "02175438839168500000000000000000000ffff0a003ee4fc3499",
    "result": {
        "data": [
            {
                "id": "uid_001",
                "fields": {
                    "f_text": "向量是指在数学中具有一定大小和方向的量", "f_image": "tos://my_bucket/vector_1.jpg"
                },
                "score": 9.899999618530273,
                "ann_score": 9.899999618530273
            },
            {
                "id": "uid_002",
                "fields": {
                    "f_text": "向量是高中数学里的一个重要概念", "f_image": "tos://my_bucket/vector_2.jpg"
                },
                "score": 8.324234999961,
                "ann_score": 8.324234999961,
            }
        ],
        "total_return_count": 2,
        "real_text_query": "根据这个问题，找到能回答这个问题的相应文本或图片：向量是指在数学中具有一定大小和方向的量，文本、图片、音视频等非结构化数据",
        "token_usage": {
            "doubao-embedding-vision__250328": {
                "prompt_tokens":1335,
                "completion_tokens":0,
                "image_tokens":1231,
                "total_tokens":1335
            }
        }
    }
}
```


<span id="32f10776"></span>
## 视频检索

* 视频token计入image_tokens

```SQL
req_path = "/api/vikingdb/data/search/multi_modal"
req_body = {
        "collection_name": "jiangyuan_video_collection",
        "index_name": "jiangyuan_video_index",
        "text": "猫",
        "video": 
            {   
                "value": "tos://data-import/2101858484/2025_08_19_10_51_40Oheg6Pua9jaD33cVl2GhcKyjumEM7aXy/cat_video.mp4",
                "fps": 1.0,
            },
        "output_fields": [
                "f_id", "f_video"
            ],
        "need_instruction": False,
        "limit": 2
 }
```

```JSON
{
    "code": "Success",
    "message": "The API call was executed successfully.",
    "request_id": "02175574557162300000000000000000000ffff0a007af7628242",
    "result": {
        "data": [
            {
                "id": "4",
                "fields": {
                    "f_id": "4",
                    "f_video": {
                         "value": "tos://my_bucket/xxxx1.mp4",
                         "fps": 1.0,
                     }
                },
                "score": 0.9932262897491455,
                "ann_score": 0.9932262897491455
            },
            {
                "id": "1",
                "fields": {
                    "f_id": "1",
                    "f_video": {
                         "value": "tos://my_bucket/xxxx2.mp4",
                         "fps": 1.0,
                     }
                },
                "score": 0.41645175218582153,
                "ann_score": 0.41645175218582153
            }
        ],
        "total_return_count": 2,
        "real_text_query": "猫",
        "token_usage": {
            "doubao-embedding-vision__250615": {
                "prompt_tokens": 18146,
                "completion_tokens": 0,
                "image_tokens": 17892,
                "total_tokens": 18146
            }
        }
    }
}
```


<span id="5c8de2d7"></span>
# 请求模版

```Plain Text
      
"""
pip3 install volcengine
"""
import os

from volcengine.auth.SignerV4 import SignerV4
from volcengine.Credentials import Credentials
from volcengine.base.Request import Request
import requests, json

class ClientForDataApi:
    def __init__(self, ak, sk, host):
        self.ak = ak
        self.sk = sk
        self.host = host

    def prepare_request(self, method, path, params=None, data=None):
        r = Request()
        r.set_shema("https")
        r.set_method(method)
        r.set_connection_timeout(10)
        r.set_socket_timeout(10)
        mheaders = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Host': self.host,
        }
        r.set_headers(mheaders)
        if params:
            r.set_query(params)
        r.set_host(self.host)
        r.set_path(path)
        if data is not None:
            r.set_body(json.dumps(data))
        credentials = Credentials(self.ak, self.sk, 'vikingdb', 'cn-beijing')
        SignerV4.sign(r, credentials)
        return r
        
    def do_req(self, req_method, req_path, req_params, req_body):
        req = self.prepare_request(method=req_method, path=req_path, params=req_params, data=req_body)
        return requests.request(method=req.method, url="http://{}{}".format(self.host, req.path),
                                  headers=req.headers, data=req.body, timeout=10000)

if __name__ == '__main__':
    client = ClientForDataApi(
        ak = "*",#替换为您的ak
        sk = "*",#替换为您的sk
        host = "api-vikingdb.vikingdb.cn-beijing.volces.com",#替换为您所在的域名
    )
    req_method = "POST"
    req_params = None
    req_path = "/api/vikingdb/data/search/multi_modal"
    req_body = {
        "collection_name": "test_coll_with_vectorize",
        "index_name": "idx_1",
        "text": "向量是指在数学中具有一定大小和方向的量，文本、图片、音视频等非结构化数据",
        "need_instruction": true,
        "output_fields": [
            "f_text"
        ],
        "limit": 2
    }
    result = client.do_req(req_method=req_method, req_path=req_path, req_params=req_params, req_body=req_body)
    print("req http status code: ", result.status_code)
    print("req result: \n", result.text)
```


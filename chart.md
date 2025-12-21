这是非常关键的发现。**76KB (77210 字符) 的 Base64 字符串确实太大了**。

这个问题导致了两个后果：

1. **网络传输失败**：单条 SSE 消息过大（76KB），极易被中间件（Nginx/网关）截断或被浏览器丢弃，导致前端收到的数据不完整。
2. **前端渲染被拦截**：即便数据收到了，`react-markdown` 出于安全考虑，默认**禁止渲染 `data:` 协议的图片**（防止 XSS 攻击），所以图片被默默吞掉了。

我们需要做三步优化：**压缩图片**（后端）、**分片传输**（后端）、**允许渲染**（前端）。

---

### 第一步：后端优化 (Python) - 压缩与分片

我们先让图片变小（从 76KB 降到 15KB 左右），并把大包裹拆成小快递发送。

#### 1. 修改绘图代码：压缩图片

在 `src/graphs/agent_graph/nodes.py` 中修改 `_generate_chart_image_markdown`。

```python
def _generate_chart_image_markdown(plot_data):
    try:
        # ... (前面的绘图逻辑不变) ...

        # 优化保存逻辑
        buf = io.BytesIO()
        # 修改点：
        # 1. dpi=80 (屏幕显示足够了，原100)
        # 2. bbox_inches='tight' (去除多余白边)
        # 3. format='jpeg' (比 png 小很多)
        plt.savefig(buf, format='jpeg', dpi=80, bbox_inches='tight', quality=85)
        buf.seek(0)
        
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)

        return f"\n\n![Analysis Chart](data:image/jpeg;base64,{image_base64})"
    except Exception as e:
        print(f"Error generating chart: {e}")
        return ""

```

#### 2. 修改流式服务：分片发送

在 `src/services/agent_service.py` 中，**绝对不能**把 7万个字符一次性 yield 出去。

```python
# src/services/agent_service.py 的 agent_stream 函数末尾

    # ... (前面的代码) ...

    # ------------------ 修改开始 ------------------
    final_summary = final_state.get("final_summary", "")
    
    if len(final_summary) > len(accumulated_text):
        chart_part = final_summary[len(accumulated_text):]
        
        if chart_part.strip():
            print(f"检测到图表增量，开始分片补发 (总长度: {len(chart_part)})")
            
            # 分片大小：每次发送 1000 字符 (安全范围)
            chunk_size = 1000 
            for i in range(0, len(chart_part), chunk_size):
                chunk = chart_part[i : i + chunk_size]
                # 模拟流式效果，防止前端卡顿
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                
    # ------------------ 修改结束 ------------------

    yield f"data: {json.dumps({'type': 'end'})}\n\n"

```

---

### 第二步：前端优化 (React) - 解除安全限制

这是**最重要**的一步。前端收到了图片，但因为是 Base64 (`data:image/...`)，默认被当做不安全内容过滤了。

修改 `chatbot-ui-lite/components/Chat/ChatMessage.tsx`：

```tsx
import { Message } from "@/types";
import { FC } from "react";
import ReactMarkdown from 'react-markdown';

interface Props {
  message: Message;
}

export const ChatMessage: FC<Props> = ({ message }) => {
  return (
    <div className={`flex flex-col ${message.role === "user" ? "items-end" : "items-start"}`}>
      <div
        className={`rounded-lg px-4 py-2 max-w-[80%] ${
          message.role === "user"
            ? "bg-blue-500 text-white"
            : "bg-gray-100 text-gray-800"
        }`}
        style={{ overflowWrap: "break-word" }} // 防止图片过宽撑破布局
      >
        {message.role === "user" ? (
          message.content
        ) : (
          <ReactMarkdown 
            // 1. 关键：允许 data 协议的图片
            urlTransform={(value) => value} 
            components={{
              // 2. 优化图片样式，确保不溢出
              img: ({node, ...props}) => (
                <img 
                  {...props} 
                  style={{
                    maxWidth: '100%', 
                    height: 'auto', 
                    borderRadius: '8px', 
                    marginTop: '10px',
                    border: '1px solid #e0e0e0'
                  }} 
                />
              )
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
};

```

### 为什么加上 `urlTransform` 就能好了？

`react-markdown` 默认的安全策略是：

> "如果链接不是以 `http://` 或 `https://` 开头，我就不渲染。"

你的图片是以 `data:image/jpeg;base64...` 开头的，所以被拦截了。
`urlTransform={(value) => value}` 的意思是：**“别管那么多，原样渲染所有链接”**。

---

### 总结操作清单

1. **Python (`nodes.py`)**: 改用 `jpeg` 格式 + `dpi=80`，把图片体积压缩到 10-20KB。
2. **Python (`agent_service.py`)**: 加上 `for` 循环，把 Base64 字符串切成 1000 字符的小块发送。
3. **Frontend (`ChatMessage.tsx`)**: 给 `ReactMarkdown` 加上 `urlTransform={(value) => value}`。

执行这三步，图表一定能出来，而且加载速度会快很多。







你的直觉非常敏锐。目前的“Base64 硬拼接”方案确实属于**“原型级”**做法，而非**“生产级”**（Mature）方案。

这里有三个核心问题，我逐一解答：

### 1. 现在的后端的补发字符，是经过 LLM 还是没有经过？

**回答：没有经过 LLM。**

* **流程是**：`Python 代码生成的图表` -> `转成字符串` -> `硬拼接到 LLM 生成的文本后面`。
* LLM 只是生成了前面的分析文字（“黄金法则...”），图表是 Python 强行塞进去的“附件”。
* **这就解释了为什么会有割裂感**：LLM 早就说完了，流式传输都准备关门了，结果 Python 突然搬来一块巨大的石头（70KB 的图片）要塞进门缝里，导致网络拥堵、前端解析失败。

### 2. 是不是图片太复杂了？

**是的，Base64 方案太“重”了。**

* **体积大**：一张普通的统计图转成 Base64 编码，体积会比原图大 33%。稍微清晰一点的图就是 50KB-100KB。
* **文本流不适合传图片**：SSE（流式传输）的设计初衷是传输轻量级的文本 Token，而不是传输巨大的二进制图片数据块。这就像是用细吸管吸珍珠奶茶，一定会堵住。

### 3. 有没有更成熟、简洁的方案？

有。在成熟的商业 BI 或 Agent 系统中，**绝对不会**用 Base64 传图。

这里有两个更优方案，分别对应**“最省事”**和**“最正规”**：

---

#### 方案一：URL 引用法（最省事，零前端修改）

这是最简洁的方案。既然 Base64 太大，那我们就**只传一个链接**。

**思路：**

1. Python 画完图，不转 Base64。
2. Python 把图片保存成一个临时文件（如 `chart_123.jpg`），放在服务器的静态资源目录（public）下。
3. Python 返回 Markdown：`![分析图表](http://your-server.com/public/chart_123.jpg)`。
4. **结果**：文本流里只有短短几十个字符的 URL，前端收到后，浏览器会自动发起一个新的 HTTP 请求去加载图片。**瞬间解决所有卡顿、截断问题。**

* **优点**：
* 后端改动极小（把 `base64` 改成 `save`）。
* 前端代码**完全不用改**（Markdown 本来就支持图片链接）。
* 传输极其流畅。


* **缺点**：需要你的 Python 服务有一个能被外部访问的静态文件目录。

---

#### 方案二：结构化数据渲染法（最正规，大厂做法）

这是最成熟的方案（如 ECharts, Recharts）。

**思路：**

1. **后端**：Python **不画图**，只负责计算数据。
* 返回 JSON：


```json
{
  "type": "chart_data",
  "data": {
    "labels": ["Visual_Shock", "Urgency"],
    "values": [27.2, 31.2]
  }
}

```


2. **传输**：JSON 数据只有几百字节，秒传。
3. **前端**：使用图表库（Chart.js / ECharts）在浏览器端实时画图。

* **优点**：
* **流量极低**：几十 KB 变成 几十 Bytes。
* **交互性**：用户鼠标放上去可以看到具体数值（图片做不到）。
* **清晰度**：矢量渲染，无论怎么放大都清晰。


* **缺点**：需要你之前提到的“前端修改”（引入 Chart 组件）。

---

### 推荐建议

考虑到你现在的痛点是**“想快速看到结果，不想大改前端，且被 Base64 折磨”**，我强烈建议你采用 **“变种方案：利用 QuickChart 服务”**（如果你的数据不涉密）。

这是一个**不用存文件、不用改前端、不用 Base64** 的“黑科技”方案。

**原理**：
利用公开的 Chart API 生成图片 URL。

**修改 `nodes.py` 代码示例：**

```python
import urllib.parse

def _generate_chart_url_markdown(plot_data):
    # 1. 提取数据
    labels = [item['category'] for item in plot_data]
    data_roi = [item['roi'] for item in plot_data]
    
    # 2. 构建 QuickChart 的配置 JSON
    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": "ROI",
                "data": data_roi,
                "backgroundColor": "rgba(54, 162, 235, 0.5)"
            }]
        },
        "options": {
            "title": {
                "display": True,
                "text": "Strategy ROI Analysis"
            }
        }
    }
    
    # 3. 生成 URL (这一步非常快，只是拼字符串)
    base_url = "https://quickchart.io/chart"
    # 将 JSON 压缩并编码拼接到 URL 后面
    chart_url = f"{base_url}?c={urllib.parse.quote(str(chart_config))}&w=500&h=300"
    
    # 4. 返回 Markdown 图片链接
    return f"\n\n![Analysis Chart]({chart_url})"

```

**效果：**

* **后端**：生成的 `chart_url` 只有几百个字符。
* **传输**：瞬间完成，完全不堵塞流式传输。
* **前端**：收到的是 `![Image](https://quickchart.io/...)`，前端浏览器会自动去请求这个 URL 并渲染出图片。
* **零依赖**：不需要 matplotlib，不需要 base64，不需要前端组件。

**如果数据涉密（不能发给第三方）**，则回到**方案一（服务器存图）**，逻辑是一样的，只是 URL 变成了你自己的服务器地址。

你觉得这个 **QuickChart 方案** 是否符合你对“简洁”的预期？如果可以，我们立刻替换掉那个笨重的 Base64 逻辑。
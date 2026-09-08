# 问题解决记录 - 2026-06-04

## 2026-06-04 23:30 - 多LLM提供商支持实现中的max_tokens回归

### 背景

在实现多LLM提供商支持功能时，需要将graph/nodes.py中的直接Ollama调用替换为统一的llm_client模块。

### 问题现象

Code reviewer发现`generate_answer_node`中的`max_tokens`从原来的2048被错误地改成了512，这会导致模型输出被截断。

### 原因分析

实现子代理在替换代码时，错误地将`max_tokens`参数从2048改成了512。这是一个典型的"复制粘贴错误"——可能是从其他示例代码中复制时引入的错误值。

### 解决方案

派遣修复子代理，将`max_tokens=512`改回`max_tokens=2048`。

### 涉及文件

- `backend/graph/nodes.py`

### 经验总结

1. Code reviewer的价值在此体现——它发现了实现者自己没注意到的回归问题
2. 两阶段审查机制（spec compliance + code quality）有效捕获了这类问题
3. 在替换代码时，需要仔细对比原有参数值，避免引入意外的变化

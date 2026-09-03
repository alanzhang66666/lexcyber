from tools.gateway import ToolGateway


class ToolAgent:
    def __init__(self, tools: ToolGateway):
        self.tools = tools

    def retrieve(self, query: str):
        return self.tools.call("retrieval.search", {"query": query, "top_k": 5})

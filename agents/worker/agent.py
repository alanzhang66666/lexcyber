from models.gateway import ModelGateway
from models.schemas import ModelRequest
from prompts.registry import PromptRegistry


class WorkerAgent:
    def __init__(self, model: ModelGateway, prompts: PromptRegistry):
        self.model = model
        self.prompts = prompts

    def run(self, user_query: str, retrieved_context: str = ""):
        prompt = self.prompts.get("worker_general_v1")
        content = f"{prompt.content}\n\n用户任务：{user_query}\n\n检索上下文：{retrieved_context or '无'}"
        return self.model.invoke(ModelRequest(task_type="general", messages=[{"role": "user", "content": content}]))

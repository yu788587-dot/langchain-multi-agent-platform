"""AgentState：贯穿整个工作流的共享状态。"""
import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict):
    question: str                         # 用户原始问题
    plan: list[dict[str, Any]]            # 规划者产出的步骤列表
    steps_results: list[dict[str, Any]]   # 执行者逐步产出的结果
    revision_count: int                   # 已执行修订的次数
    review: dict[str, Any] | None         # 审核者结论 {verdict, feedback}
    final_answer: str                     # 最终答案（含医疗免责声明）
    messages: Annotated[list[Any], operator.add]  # 过程事件流水（追加式 reducer）

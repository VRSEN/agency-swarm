import json
from typing import Any
from uuid import uuid4

from openai.types.beta.threads.message import Message
from openai.types.beta.threads.run import RequiredActionFunctionToolCall, Run
from openai.types.beta.threads.runs.tool_call import ToolCall

from agency_swarm.messages.message_output import MessageOutput
from agency_swarm.util.tracking import get_callback_handler
from agency_swarm.util.tracking.langchain_types import AgentAction


class TrackingManager:
    def __init__(self):
        self.callback_handler = get_callback_handler()

    def track_tool_start(
        self,
        tool_call: ToolCall,
        run: Run,
        agent_name: str,
        recipient_agent_name: str,
        is_retriever: bool = False,
    ) -> None:
        """Track the start of a tool/retriever execution."""
        if not self.callback_handler:
            return

        metadata = {
            "agent_name": agent_name,
            "recipient_agent_name": recipient_agent_name,
            "run_status": run.status,
            "ls_model_name": run.model,
        }

        if is_retriever:
            self.callback_handler.on_retriever_start(
                serialized={"name": tool_call.function.name},
                query=tool_call.function.arguments,
                run_id=tool_call.id,
                parent_run_id=run.id,
                metadata=metadata,
            )
        else:
            self.callback_handler.on_tool_start(
                serialized={"name": tool_call.function.name},
                input_str=tool_call.function.arguments,
                run_id=tool_call.id,
                parent_run_id=run.id,
                metadata=metadata,
            )

    def track_tool_end(
        self,
        output: Any,
        tool_call: ToolCall,
        parent_run_id: str,
        is_retriever: bool = False,
    ) -> None:
        """Track the successful completion of a tool/retriever execution."""
        if not self.callback_handler:
            return

        if is_retriever:
            self.callback_handler.on_retriever_end(
                documents=output if isinstance(output, list) else [],
                run_id=tool_call.id,
                parent_run_id=parent_run_id,
            )
        else:
            self.callback_handler.on_tool_end(
                output=str(output),
                run_id=tool_call.id,
                parent_run_id=parent_run_id,
            )

    def track_tool_error(
        self,
        error: Exception,
        tool_call: ToolCall,
        parent_run_id: str,
        is_retriever: bool = False,
    ) -> None:
        """Track an error during tool/retriever execution."""
        if not self.callback_handler:
            return

        if is_retriever:
            self.callback_handler.on_retriever_error(
                error=error,
                run_id=tool_call.id,
                parent_run_id=parent_run_id,
            )
        else:
            self.callback_handler.on_tool_error(
                error=error,
                run_id=tool_call.id,
                parent_run_id=parent_run_id,
            )

    def track_agent_actions(
        self,
        tool_calls: list[RequiredActionFunctionToolCall],
        run_id: str,
        parent_run_id: str | None = None,
    ) -> None:
        """Send agent_action before each tool call."""
        if not self.callback_handler:
            return

        for tc in tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            action = AgentAction(
                tool=tc.function.name,
                tool_input=args,
                log="",
            )
            self.callback_handler.on_agent_action(
                action=action,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )

    def track_chain_error(
        self, error: Exception, run_id: str, parent_run_id: str | None = None
    ) -> None:
        """Track chain errors."""
        if not self.callback_handler:
            return

        self.callback_handler.on_chain_error(
            error=error,
            run_id=run_id,
            parent_run_id=parent_run_id,
        )

    def start_chain(self, message: str, chain_name: str) -> str:
        """Start tracking for a top-level chain (e.g. Agency.get_completion).
        Returns the run_id if tracking is enabled, None otherwise."""
        run_id = f"chain_{uuid4()}"
        if not self.callback_handler:
            return

        self.callback_handler.on_chain_start(
            serialized={"name": chain_name, "id": [run_id]},
            inputs={"message": message},
            run_id=run_id,
            metadata={"agency_class": "Agency"},
        )

        return run_id

    def end_chain(
        self, final_output: Any, run_id: str, parent_run_id: str | None = None
    ) -> None:
        """End tracking for a top-level chain."""
        if not self.callback_handler:
            return

        self.callback_handler.on_chain_end(
            outputs={"response": final_output},
            run_id=run_id,
            parent_run_id=parent_run_id,
        )

    def start_run(
        self,
        message: str | list[dict] | None,
        sender_agent: str,
        recipient_agent: str,
        model: str,
        run_id: str,
        parent_run_id: str | None,
        message_obj: Message | None = None,
        temperature: float | None = None,
    ) -> None:
        """Track the start of a run."""
        if not self.callback_handler:
            return

        prompts = [str(m) for m in message] if isinstance(message, list) else [message]

        metadata = {
            "agent_name": sender_agent,
            "recipient_agent_name": recipient_agent,
            "run_status": "running",
            "ls_model_name": model,
            "message_obj": message_obj.model_dump() if message_obj else {},
        }
        invocation_params = {
            "_type": "openai",
            "model": model,
            "temperature": temperature,
        }

        self.callback_handler.on_llm_start(
            serialized={
                "name": f"Thread: {sender_agent} -> {recipient_agent}",
                "id": [run_id],
            },
            prompts=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
            invocation_params=invocation_params,
        )

    def end_run(
        self,
        message_output: MessageOutput,
        run_id: str,
        parent_run_id: str | None = None,
    ) -> None:
        """Track the end of a run with a message output."""
        if not self.callback_handler:
            return

        from langchain_core.outputs import Generation, LLMResult

        generation = Generation(text=message_output.content)

        result = LLMResult(generations=[[generation]])

        metadata = {
            "message_obj": message_output.obj.model_dump() if message_output.obj else {}
        }

        self.callback_handler.on_llm_end(
            response=result,
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
        )

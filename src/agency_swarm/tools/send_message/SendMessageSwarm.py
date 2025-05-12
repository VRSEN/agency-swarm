from .SendMessage import SendMessageBase


class SendMessageSwarm(SendMessageBase):
    """DEPRECATED: Use the Agents SDK handoff mechanism instead. This tool will be removed in a future version."""

    class ToolConfig:
        # set output as result because the communication will be finished after this tool is called
        output_as_result: bool = True
        one_call_at_a_time: bool = True

    def run(self) -> str:
        raise DeprecationWarning(
            "SendMessageSwarm is deprecated and will be removed in a future version. "
            "Please use the Agents SDK handoff mechanism."
        )

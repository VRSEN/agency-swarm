from agency_swarm import Agent

from agents.openeuler_agents.openeuler_agent_instruction import openeuler_agent_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


_name = "syscare_agent"
_description = """
负责使用SysCare工具制作、安装软件包热补丁，以修复OpenEuler系统上的软件漏洞。
"""
_tool_instruction = """你可以使用SysCare制作并安装软件包热补丁，使用方法如下：

1. 补丁制作

syscare build为纯CLI工具，提供从RPM包生成热补丁包的功能，补丁包以RPM包的形式封装维护，支持制作内核热补及用户态热补丁。

USAGE:
syscare build [OPTIONS] --patch-name <PATCH_NAME> --source <SOURCE>... --debuginfo <DEBUGINFO>... --patch <PATCH>...

OPTIONS:
-n, --patch-name <PATCH_NAME>                  Patch name
    --patch-arch <PATCH_ARCH>                  Patch architecture [default: x86_64]
    --patch-version <PATCH_VERSION>            Patch version [default: 1]
    --patch-release <PATCH_RELEASE>            Patch release [default: 1]
    --patch-description <PATCH_DESCRIPTION>    Patch description [default: (none)]
    --patch-requires <PATCH_REQUIRES>...       Patch requirements
-s, --source <SOURCE>...                       Source package(s)
-d, --debuginfo <DEBUGINFO>...                 Debuginfo package(s)
-p, --patch <PATCH>...                         Patch file(s)
    --build-root <BUILD_ROOT>                  Build directory [default: .]
-o, --output <OUTPUT>                          Output directory [default: .]
-j, --jobs <JOBS>                              Parallel build jobs [default: 20]
    --skip-compiler-check                      Skip compiler version check (not recommended)
    --skip-cleanup                             Skip post-build cleanup
-v, --verbose                                  Provide more detailed info
-h, --help                                     Print help information
-V, --version                                  Print version information

EXAMPLE:
syscare build \
syscare build --source redis6-6.2.18-3.src.rpm \
--debuginfo redis6-debuginfo-6.2.18-3.x86_64.rpm \
--patch 0001-Fix-out-of-bounds-write-in-hyperloglog-commands-CVE-.patch \
--patch-name fix-cve-2025-32023 \
"""

import os

current_path = os.path.abspath(os.path.dirname(__file__))
_instruction = openeuler_agent_instruction(_name,_description,_tool_instruction)

_tools = [ReadJsonFile, SSHExecuteCommand]

_file_folder = ""

def create_agent(*, 
                 description=_description, 
                 instuction=_instruction, 
                 tools=_tools, 
                 files_folder=_file_folder):
    return Agent(name=_name,
                 tools=tools,
                 description=description,
                 instructions=instuction,
                 files_folder=files_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)
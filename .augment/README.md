# AugmentCode Configuration for Agency Swarm

This directory contains configuration files for AugmentCode integration with the Agency Swarm project.

## 📁 File Structure

```
.augment/
├── README.md          # This file - overview and usage
├── config.yaml        # Main AugmentCode configuration
├── rules.md           # Detailed coding rules and constraints
├── context.md         # Project context and architecture
└── examples.md        # Code examples and patterns
```

## 🎯 Purpose

These configuration files ensure that AugmentCode (and other AI coding assistants) work optimally with the Agency Swarm codebase by:

1. **Enforcing project standards** from `AGENTS.md` and `pyproject.toml`
2. **Providing architectural context** about the multi-agent framework
3. **Defining mandatory workflows** for safe code changes
4. **Establishing quality gates** for testing and validation
5. **Documenting patterns** for common development tasks

## 🔧 Configuration Files

### `config.yaml`
Main configuration file containing:
- Project metadata and structure
- AI assistant principles and workflow
- Code quality standards and tools
- Architecture constraints
- Development environment setup
- Security and integration patterns

### `rules.md`
Detailed rules derived from `AGENTS.md`:
- **Critical principles** (tests define truth, guardian of codebase)
- **Mandatory workflow** (make prime, validation steps)
- **File requirements** (size limits, naming conventions)
- **Technology stack** (Python 3.12+, UV, pytest, ruff, mypy)
- **Prohibited practices** (what never to do)
- **Testing standards** (coverage targets, test structure)

### `context.md`
Project context and architecture:
- **Project overview** and key features
- **Architecture summary** with core components
- **Communication patterns** between agents
- **Development standards** and current issues
- **Technology stack** and dependencies
- **Integration points** with external services

### `examples.md`
Code examples and patterns:
- **Basic agency creation** patterns
- **Tool development** (function_tool, BaseTool, OpenAPI)
- **Advanced patterns** (persistence, structured output, FastAPI)
- **Testing patterns** (unit tests, integration tests)
- **Common patterns** (error handling, file management)

## 🚀 Usage

### For AI Coding Assistants

These files are automatically loaded by AugmentCode and provide context for:
- Understanding project architecture
- Following established patterns
- Maintaining code quality standards
- Implementing proper testing workflows
- Avoiding common pitfalls

### For Developers

Reference these files when:
- **Onboarding** new team members
- **Contributing** to the project
- **Understanding** architectural decisions
- **Following** development workflows
- **Maintaining** code quality

## 🔴 Critical Workflows

### Before Making Changes
```bash
make prime  # MANDATORY - builds context and reviews diffs
```

### Development Cycle
```bash
# 1. Make focused changes
# 2. Run relevant tests
uv run pytest tests/specific_module/ -v

# 3. Validate with linting
make lint

# 4. Check types
make mypy

# 5. Full validation before completion
make ci
```

### Testing Requirements
- **Unit tests**: 87%+ coverage target
- **Integration tests**: Real API interactions
- **Test structure**: Organized by module
- **Test quality**: Deterministic, minimal, precise assertions

## 🛡️ Safety Protocols

### Guardian Principles
1. **Question First**: Verify alignment with existing patterns
2. **Defend Consistency**: Require justification for deviations
3. **Think Critically**: Default to codebase conventions
4. **Evidence-Driven**: Justify changes with tests/logs/specs

### Prohibited Practices
- Ending work without testing changes
- Skipping workflow safety steps
- Introducing functional changes during refactoring
- Using global interpreters (always use `uv run`)
- Editing package files manually

## 📊 Quality Standards

### Code Metrics
- **File size**: ≤ 500 lines
- **Method size**: ≤ 100 lines
- **Test coverage**: ≥ 87%
- **Python version**: 3.12+ (development on 3.13)
- **Line length**: 120 characters

### Tools Configuration
- **Linting**: ruff with project config
- **Type checking**: mypy (targeting strict mode)
- **Testing**: pytest with asyncio support
- **Formatting**: ruff format
- **Package management**: UV (not pip)

## 🔗 Integration Points

### OpenAI Agents SDK
- Extends base `Agent` class
- Uses `FunctionTool` format
- Leverages SDK's execution logic
- Supports sync/async operations

### External Services
- **OpenAI API**: Core model interactions
- **Vector Stores**: File search capabilities
- **MCP Servers**: Model Context Protocol
- **FastAPI**: Web interface (optional)

## 📚 Related Files

### Project Root
- `.cursorrules` - Cursor IDE specific rules
- `AGENTS.md` - Detailed agent development guidelines
- `pyproject.toml` - Python project configuration
- `Makefile` - Development commands
- `.pre-commit-config.yaml` - Git hooks configuration

### Documentation
- `docs/` - Mintlify-based documentation
- `examples/` - Runnable code examples
- `README.md` - Project overview
- `CONTRIBUTING.md` - Contribution guidelines

## 🔄 Maintenance

### Updating Configuration
When project standards change:
1. Update relevant configuration files
2. Ensure consistency across all `.augment/` files
3. Test with AI assistant to verify effectiveness
4. Update examples if patterns change

### Version Alignment
Keep configuration synchronized with:
- `pyproject.toml` dependencies and settings
- `AGENTS.md` rules and workflows
- `.cursorrules` patterns and constraints
- Project architecture evolution

## 🎯 Success Metrics

Configuration is effective when:
- ✅ AI assistants follow established patterns
- ✅ Code quality remains consistently high
- ✅ Tests pass reliably (≥99% success rate)
- ✅ Coverage targets are met (≥87%)
- ✅ No prohibited practices are introduced
- ✅ Architectural consistency is maintained

## 🆘 Troubleshooting

### Common Issues
1. **Tests failing**: Check `.env` file has `OPENAI_API_KEY`
2. **Type errors**: Run `make mypy` to see specific issues
3. **Lint failures**: Run `make format` to auto-fix
4. **Coverage low**: Add tests for uncovered modules
5. **Large files**: Refactor into smaller, focused modules

### Getting Help
- Check `CONTRIBUTING.md` for development setup
- Review `examples/` for usage patterns
- Run `make help` for available commands
- Consult `docs/` for detailed documentation

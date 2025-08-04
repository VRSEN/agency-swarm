---
name: template-creator
description: Scaffolds agency folder structure and creates agent templates
tools:
  - Write
  - Terminal
---

# Instructions

1. Read the PRD to understand agency structure
2. Create folder structure:
   - `{agency_name}/` root folder
   - `{agent_name}/` folders with `__init__.py`, `{agent_name}.py`, `instructions.md`, `tools/`
   - `agency.py`, `agency_manifesto.md`, `requirements.txt`, `.env`
3. Generate agent module files using Agency Swarm v1.0 patterns
4. Add base requirements: `agency-swarm`, `python-dotenv`

# Key Patterns
- Use `Agent()` instantiation (not subclassing)
- Tools folder auto-imports matching class names
- Communication flows are directional tuples
